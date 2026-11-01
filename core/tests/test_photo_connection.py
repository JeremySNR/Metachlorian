"""The folder-first Lightroom workflow, without a local RAW decoder or Adobe runtime."""
import io
from pathlib import Path

import pytest
from PIL import Image

from metachlorian.auth import LOCAL_ADMIN, Principal
from metachlorian.photos import images
from metachlorian.photos.errors import PhotoConflict
from .test_photos import photos, run  # noqa: F401


def folder_photo(service, bridge):
    # Remove only the catalogue association to reproduce an existing folder index.
    service.db.x('UPDATE photos SET catalog_uid=NULL,lr_id=NULL,revision=?', ('folder-fingerprint',))
    original = Path(bridge.photos['1']['path'])
    raw = original.with_suffix('.ARW')
    original.rename(raw)  # JPEG bytes stand in for Adobe's decoded rendition.
    service.db.x('UPDATE assets SET path=?,filename=?', (str(raw), raw.name))
    service.db.x('UPDATE asset_paths SET path=?', (str(raw),))
    bridge.photos['1'].update(path=str(raw), filename=raw.name)
    bridge.catalog['version'] = '14.2'


def test_folder_raw_uses_existing_lightroom_master_and_creative_copy(photos, monkeypatch):
    service, bridge, uid = photos
    folder_photo(service, bridge)
    calls = []
    call = bridge.call
    def track(action, args=None, **kwargs):
        calls.append(action)
        return call(action, args, **kwargs)
    monkeypatch.setattr(bridge, 'call', track)
    monkeypatch.setattr(images, 'decode', lambda *a, **k: pytest.fail('RAW must come from Lightroom'))
    data, info = service.preview(LOCAL_ADMIN, uid)
    assert Image.open(io.BytesIO(data)).size == (120, 80)
    assert info['provenance']['source'] == 'lightroom_preview'
    assert service._row(uid)['lr_id'] == '1'
    assert service.db.q1('SELECT COUNT(*) FROM photos')[0] == 1
    ctx = service.context(LOCAL_ADMIN, uid)
    assert ctx['workflow']['state'] == 'ready' and ctx['capabilities']['editing']
    assert 'mc_import' not in calls and 'mc_begin' not in calls
    original_settings = bridge.meta('1')['settings']
    queued = service.begin(LOCAL_ADMIN, [uid], {uid: ctx['revision']}, 'creative', 'Warm Kodak-inspired family photograph', creative=True)
    session = run(service, queued)['result']['sessions'][0]
    applied = run(service, service.apply(LOCAL_ADMIN, session['session_id'], session['revision'], [{'op': 'settings', 'values': {'Exposure2012': -.3}}], 'warm-gold'))
    assert applied['status'] == 'done'
    assert bridge.meta('1')['settings'] == original_settings
    assert 'mc_import' not in calls
    status = service.check_connection(LOCAL_ADMIN)
    assert status['lightroom']['can_edit'] and status['lightroom']['catalog']['version'] == '14.2'
    assert status['coverage']['folder_only'] == 0


def test_unmatched_folder_explains_import_and_missing_connection(photos):
    service, bridge, uid = photos
    folder_photo(service, bridge)
    bridge.photos['1']['path'] = '/another/file.ARW'
    context = service.context(LOCAL_ADMIN, uid)
    assert context['import_on_edit'] and context['workflow']['state'] == 'import_required'
    assert context['capabilities']['editing'] and context['capabilities']['controls_after_import']
    assert not service._row(uid)['catalog_uid']
    bridge.online = False
    context = service.context(LOCAL_ADMIN, uid)
    assert context['workflow']['state'] == 'blocked'
    assert not context['capabilities']['editing']
    assert context['capabilities']['reason']
    Path(service._row(uid)['path']).unlink()
    bridge.online = True
    missing = service.context(LOCAL_ADMIN, uid)
    assert missing['workflow']['state'] == 'blocked'
    assert 'original file is unavailable' in missing['capabilities']['reason']


def test_folder_matching_rejects_wrong_file_and_catalogue(photos, monkeypatch):
    service, bridge, uid = photos
    folder_photo(service, bridge)
    monkeypatch.setattr(bridge, 'call', lambda *a, **k: {'catalog': {'uid': 'different'}, 'photo': bridge.meta('1')})
    with pytest.raises(PhotoConflict, match='catalogue changed'):
        service.context(LOCAL_ADMIN, uid)
    monkeypatch.setattr(bridge, 'call', lambda *a, **k: {'catalog': bridge.catalog, 'photo': {**bridge.meta('1'), 'is_virtual': True}})
    with pytest.raises(PhotoConflict, match='different photograph'):
        service.context(LOCAL_ADMIN, uid)
    assert not service._row(uid)['catalog_uid']


def test_readiness_distinguishes_files_from_connection_and_permissions(photos):
    service, bridge, uid = photos
    status = service.status(LOCAL_ADMIN)
    assert not status['connector']['files_copied']
    service.install_connector(LOCAL_ADMIN)
    bridge.online = False
    status = service.status(LOCAL_ADMIN)
    assert status['connector']['files_current'] and not status['lightroom']['connected']
    bridge.online = True
    reader = Principal(None, 'reader', 'viewer', {'library:read'})
    status = service.status(reader)
    assert status['lightroom']['connected'] and not status['lightroom']['can_edit']
    assert 'photos:edit' in status['lightroom']['message']
