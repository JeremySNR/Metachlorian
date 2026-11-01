"""Public interfaces and failure recovery; Lightroom itself is simulated here."""
import base64
import io
import json
from pathlib import Path

import anyio
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from metachlorian import auth, people, models
from metachlorian.api.app import create_app
from metachlorian.photos import analysis, store
from metachlorian.photos.controls import CONTROLS
from metachlorian.photos.errors import LightroomUnavailable, PhotoConflict
from metachlorian.service import Library
from .test_photos import photos, begin, run  # shared fake Adobe adapter fixture


def test_api_contract_images_permissions_and_workflow(photos):
    service, bridge, uid = photos
    app = create_app(service.settings, service.db, start_workers=False)
    app.state.lib._photos = service
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 5010)) as client:
        headers = {'X-Metachlorian': '1'}
        assert client.post('/api/photos/search', json={}).status_code == 403
        assert client.post('/api/photos/search', json={'query': 'holiday'}, headers=headers).json()['results'][0]['uid'] == uid
        assert client.post('/api/photos/search', json={'unknown': True}, headers=headers).status_code == 422
        assert client.post('/api/photos/search', json={'filters': {'unknown': True}}, headers=headers).status_code == 400
        ctx = client.get(f'/api/photos/{uid}/context').json()
        image = client.get(f'/api/photos/{uid}/preview', params={'revision': ctx['revision']})
        assert image.status_code == 200 and image.headers['cache-control'] == 'no-store'
        assert Image.open(io.BytesIO(image.content)).format == 'JPEG'
        assert client.get(f'/api/photos/{uid}/preview?region=0,0,0,1').status_code == 400
        assert client.get(f'/api/photos/{uid}/preview?revision=stale').status_code == 409
        body = {'photo_ids': [uid], 'expected_revisions': {uid: ctx['revision']}, 'idempotency_key': 'api-begin'}
        job = client.post('/api/photos/edits', json=body, headers=headers).json()
        session = run(service, job)['result']['sessions'][0]
        assert client.post('/api/photos/edits', json=body, headers=headers).json()['uid'] == job['uid']
        assert client.get(f"/api/photos/jobs/{job['uid']}").json()['status'] == 'done'
        edit = client.post(f"/api/photos/edits/{session['session_id']}/apply", json={
            'expected_revision': session['revision'], 'operations': [{'op': 'settings', 'values': {'Exposure2012': .2}}], 'idempotency_key': 'api-edit'}, headers=headers).json()
        changed = run(service, edit)
        assert changed['status'] == 'done'
        saved = client.post('/api/photos/edits/finish', json={'selections': [{'session_id': session['session_id'], 'reviewed_revision': changed['result']['revision']}], 'collection': 'Family', 'idempotency_key': 'api-finish'}, headers=headers).json()
        assert run(service, saved)['status'] == 'done'
        bridge.online = False
        assert client.get(f'/api/photos/{uid}/context').status_code == 503
        # No unedited-file fallback for catalogue previews.
        assert client.get(f'/api/photos/{uid}/preview?edge=1999').status_code == 503


def test_mcp_returns_real_image_blocks_and_scoped_jobs(photos, mcp_client):
    service, bridge, uid = photos
    lib = Library(service.db, service.settings)
    lib._photos = service
    readonly = auth.Principal(None, 'readonly', 'agent', set(auth.AGENT_DEFAULT), 'mcp')

    async def workflow():
        async with mcp_client(lib, readonly) as client:
            preview = await client.call_tool('get_photo_previews', {'photo_ids': [uid]})
            assert not preview.is_error
            assert [block.type for block in preview.content] == ['text', 'image']
            info = json.loads(preview.content[0].text)
            assert info['provenance']['raw_recovery_known'] is False
            assert Image.open(io.BytesIO(base64.b64decode(preview.content[1].data))).size == (120, 80)
            denied = await client.call_tool('begin_photo_edits', {'photo_ids': [uid], 'expected_revisions': {uid: info['revision']}, 'idempotency_key': 'no-scope'})
            assert denied.is_error and 'photos:edit' in denied.content[0].text
            invalid = await client.call_tool('get_photo_previews', {'photo_ids': []})
            assert invalid.is_error
        async with mcp_client(lib, auth.LOCAL_ADMIN) as client:
            context = await client.call_tool('get_photo_edit_context', {'photo_id': uid})
            assert not context.is_error and 'guidance' in context.content[0].text
            resources = await client.list_resources()
            assert any(str(r.uri) == 'metachlorian://photos/editing-guide' for r in resources.resources)
    anyio.run(workflow)


def test_baseline_render_must_complete_before_session_is_active(photos, monkeypatch):
    service, bridge, uid = photos
    original = bridge.call
    failed = False
    def call(action, *args, **kwargs):
        nonlocal failed
        if action == 'mc_render' and not failed:
            failed = True
            raise LightroomUnavailable('disconnected during baseline render')
        return original(action, *args, **kwargs)
    monkeypatch.setattr(bridge, 'call', call)
    revision = service.context(auth.LOCAL_ADMIN, uid)['revision']
    job = service.begin(auth.LOCAL_ADMIN, [uid], {uid: revision}, 'baseline-loss')
    assert run(service, job)['status'] == 'waiting'
    assert service.db.q1('SELECT status FROM photo_edit_sessions')[0] == 'creating'
    service.resume(auth.LOCAL_ADMIN, job['uid'])
    assert run(service, job)['status'] == 'done'
    assert len(bridge.copies) == 1
    assert service.db.q1('SELECT status FROM photo_edit_sessions')[0] == 'active'


def test_analysis_yields_to_edits_and_keeps_checkpoint(photos, monkeypatch):
    service, bridge, uid = photos
    row = service._row(uid)
    called = []
    def analyse(im, settings, provenance):
        called.append(im.size)
        revision = service.context(auth.LOCAL_ADMIN, uid)['revision']
        service.begin(auth.LOCAL_ADMIN, [uid], {uid: revision}, 'interactive-edit')
        return analysis.measure(im, provenance), np.ones(8, np.float32)/np.sqrt(8), []
    monkeypatch.setattr(analysis, 'analyse', analyse)
    job = service.analyse_pending(auth.LOCAL_ADMIN, 'background')
    assert run(service, job)['status'] == 'queued'
    progress = service.job(auth.LOCAL_ADMIN, job['uid'])['result']
    assert progress['last_id'] == row['id'] and progress['processed'] == 1
    service.jobs.run_once()
    assert service.db.q1("SELECT status FROM photo_jobs WHERE kind='begin'")[0] == 'done'


def test_cancel_resume_and_worker_revocation(photos):
    service, bridge, uid = photos
    actor_id = auth.create_user(service.db, 'agent', 'agent')
    token = auth.create_token(service.db, actor_id, 'edit', ['library:read', 'photos:edit'])
    actor = auth.authenticate_token(service.db, token)
    revision = service.context(actor, uid)['revision']
    job = service.begin(actor, [uid], {uid: revision}, 'revoked')
    assert service.cancel(actor, job['uid'])['status'] == 'cancelled'
    assert service.resume(actor, job['uid'])['status'] == 'queued'
    service.db.x('UPDATE tokens SET revoked=1 WHERE id=?', (actor.token_id,))
    assert run(service, job)['status'] == 'failed'
    assert not bridge.copies
    assert 'no longer active' in service.jobs.get(job['uid'])['error']


def test_people_merge_and_naming_preserve_photo_faces(photos):
    service, bridge, uid = photos
    pid = service._row(uid)['id']
    emb = np.zeros(128, np.float32); emb[0] = 1
    face = {'box': [.1,.1,.4,.5], 'embedding': emb, 'score': .99, 'size_px': 70, 'evidence': {}}
    analysis.save_faces(service.db, pid, [face])
    identity = service.db.q1('SELECT identity_id FROM photo_faces')[0]
    people.rename(service.db, identity, 'Family member', 'local')
    analysis.save_faces(service.db, pid, [])  # Temporarily crop the face out.
    assert service.db.q1('SELECT identity_id FROM photo_face_labels')[0] == identity
    analysis.save_faces(service.db, pid, [{**face, 'box': [.2,.15,.6,.65]}])
    assert service.db.q1('SELECT assigned_by FROM photo_faces')[0] == 'named'
    assert service.search(auth.LOCAL_ADMIN, filters={'person': 'Family member'})['total'] == 1
    result = people.list_people(service.db)['people'][0]
    assert result['photos'] == 1 and result['cover'].startswith('/api/photos/')
    other_emb = np.zeros(128, np.float32); other_emb[1] = 1
    target = service.db.x('INSERT INTO identities(centroid,n,created_at,updated_at) VALUES(?,1,1,1)', (other_emb.tobytes(),)).lastrowid
    people.merge(service.db, identity, target)
    assert service.db.q1('SELECT identity_id FROM photo_faces')[0] == target
    assert service.db.q1('SELECT n FROM identities WHERE id=?', (target,))[0] == 1
    people.forget(service.db, target)
    assert not service.db.q('SELECT * FROM photo_faces')
    assert not service.db.q('SELECT * FROM photo_face_labels')


def test_photo_install_does_not_fetch_audio_or_optional_runtime(photos, monkeypatch):
    service, bridge, uid = photos
    fetched = []
    def fetch(root, name, progress, on_bytes):
        fetched.append(name); on_bytes(10, 10)
    monkeypatch.setattr(models, 'fetch', fetch)
    job = service.install_models(auth.LOCAL_ADMIN, 'photo-pack')
    assert run(service, job)['status'] == 'done'
    assert set(fetched) == {'siglip-base-multilingual', 'yunet', 'sface'}
    files = service.install_connector(auth.LOCAL_ADMIN)
    assert (Path(files['path'])/'Info.lua').is_file()
    assert json.loads((Path(files['path'])/'controls.json').read_text()) == CONTROLS
    assert service.status(auth.LOCAL_ADMIN)['enabled']


def test_folder_ingest_incremental_and_no_video_jobs(photos, tmp_path, monkeypatch):
    service, bridge, uid = photos
    folder = tmp_path/'pictures'; folder.mkdir()
    for i in range(3):
        Image.new('RGB', (64, 48), (i*50, 70, 110)).save(folder/f'{i}.jpg')
    job = service.scan_folder(auth.LOCAL_ADMIN, str(folder), 'folder-scan')
    result = run(service, job)
    assert result['result']['processed'] == result['result']['changed'] == 3
    run(service, service.job(auth.LOCAL_ADMIN, result['result']['analysis_job_id']))
    assert service.cache.stats()['bytes'] <= service.cache.budget
    job2 = service.scan_folder(auth.LOCAL_ADMIN, str(folder), 'folder-again')
    assert run(service, job2)['result']['changed'] == 0
    assert not service.db.q('SELECT * FROM jobs')
    assert not service.db.q('SELECT * FROM shots')
    assert len(list(folder.iterdir())) == 3
    assert Library(service.db, service.settings).list_assets(auth.LOCAL_ADMIN)['total'] == 0
