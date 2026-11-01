"""Shared photo service for REST, MCP and the desktop application."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .. import models, rights
from ..auth import Forbidden, Principal, ROLE_SCOPES, audit, require
from ..db import dumps, loads, now
from . import analysis, images, store
from .bridge import LightroomBridge
from .cache import PreviewCache
from .controls import guidance, validate_operations
from .errors import LightroomUnavailable, PhotoConflict, PhotoError
from .jobs import PhotoJobs, YieldToEdits, job_scope
from .search import PhotoSearch
from .readiness import connector_files, connection_details, decoders


class PhotoLibrary:
    def __init__(self, db, settings, bridge=None):
        self.db, self.settings = db, settings
        self.bridge = bridge or LightroomBridge(settings.lightroom_request_port, settings.lightroom_response_port)
        self.cache = PreviewCache(settings.data_dir / 'photo-cache', settings.photo_cache_mib * 1024**2)
        self.searcher = PhotoSearch(db, settings)
        self.jobs = PhotoJobs(self)

    def _allow(self, p: Principal, scope: str = 'library:read'):
        require(p, scope)
        if not self.settings.photos_enabled:
            raise PhotoError('Enable Photos in Metachlorian before using photo tools')
        self.cache.budget = self.settings.photo_cache_mib * 1024**2

    def _row(self, uid: str) -> dict:
        row = self.db.q1('SELECT p.*,a.path,a.filename,a.width,a.height,a.size,a.uid asset_uid FROM photos p JOIN assets a ON a.id=p.asset_id WHERE p.uid=? AND p.deleted_at IS NULL', (uid,))
        if not row:
            raise PhotoError('Photo not found')
        return dict(row)

    def _media(self, p: Principal, row: dict):
        self._allow(p)
        verdict = rights.gate(rights.get_rights(self.db, row['asset_id']), principal=p, mode='media')
        # Match the existing shot-preview policy: blocked media cannot leave
        # through an agent, while unknown rights can be inspected and corrected.
        if p.is_agent and verdict.blocked:
            raise Forbidden('This photograph is blocked or its rights have expired')

    def status(self, p: Principal, *, check: bool = False) -> dict:
        require(p, 'library:read')
        counts = {r['status']: r['n'] for r in self.db.q('SELECT status,COUNT(*) n FROM photos WHERE deleted_at IS NULL GROUP BY status')}
        connection = self.bridge.status(force=check) if self.settings.photos_enabled else {'connected': False, 'code': 'photos_disabled'}
        linked = self.db.q1('SELECT COUNT(*) n FROM photos WHERE deleted_at IS NULL AND catalog_uid IS NOT NULL')['n']
        state = connection_details(connection, p.can('photos:edit'))
        return {'enabled': self.settings.photos_enabled, 'counts': counts,
                'coverage': {'total': sum(counts.values()), 'analysed': counts.get('ready', 0),
                             'needs_attention': counts.get('unavailable', 0), 'linked': linked,
                             'folder_only': sum(counts.values()) - linked},
                'connector': {**connector_files(self.settings.data_dir),
                              'ports': [self.settings.lightroom_request_port, self.settings.lightroom_response_port]}, 'decoders': decoders(),
                'agent': {'endpoint': f'http://127.0.0.1:{self.settings.port}/mcp/', 'can_edit': p.can('photos:edit'),
                          'can_save_collection': p.can('collections:write'), 'required_scopes': ['library:read', 'photos:edit', 'collections:write']},
                'catalogs': [dict(r) for r in self.db.q('SELECT * FROM photo_catalogs')],
                'folders': [dict(r) for r in self.db.q("SELECT s.uri,s.last_scan,COUNT(a.id) photos FROM sources s JOIN assets a ON a.source_id=s.id WHERE a.media_kind='photo' GROUP BY s.id")],
                'cache': self.cache.stats(), 'index_target_bytes': 2*1024**3,
                'database_bytes': sum(path.stat().st_size for path in (Path(self.db.path), Path(str(self.db.path)+'-wal')) if path.is_file()),
                'vector_cache_bytes': sum(path.stat().st_size for path in (self.settings.data_dir/'photo-index').glob('*') if path.is_file()),
                'models': [m for m in models.status(self.settings.resolved_models_dir) if m['name'] in models.PHOTO_MODELS],
                'lightroom': state,
                'storage_note': 'Originals stay in place. The database includes videos too. Model downloads and Lightroom preview/AI data are separate.',
                'validation': 'Preview release: real Lightroom Mac/Windows certification and preference benchmarks are pending.'}

    def check_connection(self, p: Principal) -> dict:
        result = self.status(p, check=True)
        audit(self.db, p, 'check_photo_connection', detail={'code': result['lightroom'].get('code'), 'connected': result['lightroom']['connected']})
        return result

    def _link_existing(self, p: Principal, row: dict, connection: dict | None = None) -> dict:
        """Match an indexed file to an existing Lightroom master; never import here."""
        if row['catalog_uid']:
            return row
        self._media(p, row)
        connection = connection if connection is not None else self.bridge.status()
        if not connection.get('connected') or not connection.get('features', {}).get('find_by_path'):
            return row
        result = self.bridge.call('mc_find_photo', {'catalog_uid': connection['catalog']['uid'], 'path': row['path']})
        if result.get('catalog', {}).get('uid') != connection['catalog']['uid']:
            raise PhotoConflict('The active Lightroom catalogue changed while matching this file')
        photo = result.get('photo')
        if not photo:
            return row
        norm = lambda value: os.path.normcase(str(Path(value).expanduser().resolve()))
        if photo.get('is_virtual') or norm(photo.get('path', '')) != norm(row['path']):
            raise PhotoConflict('Lightroom returned a different photograph for this file')
        store.catalog(self.db, result['catalog'])
        linked = store.register(self.db, row['path'], photo, catalog_uid=result['catalog']['uid'])
        audit(self.db, p, 'link_photo_to_lightroom', row['uid'], {'catalog_uid': result['catalog']['uid'], 'lr_id': photo['lr_id']})
        return self._row(linked['uid'])

    def install_connector(self, p: Principal) -> dict:
        self._allow(p, 'admin')
        source = Path(__file__).parent / 'lightroom' / 'MetachlorianPhotos.lrplugin'
        destination = self.settings.data_dir / 'lightroom' / source.name
        shutil.copytree(source, destination, dirs_exist_ok=True)
        audit(self.db, p, 'install_lightroom_connector', str(destination))
        return {'path': str(destination), 'instructions': 'In Lightroom Classic, open File → Plug-in Manager → Add, choose this folder and enable it. Restart Lightroom once if the connector has not started.',
                'ports': [self.settings.lightroom_request_port, self.settings.lightroom_response_port]}

    def search(self, p: Principal, query: str = '', filters: dict | None = None, limit: int = 40, cursor: str | None = None, diverse: bool = True) -> dict:
        self._allow(p)
        result = self.searcher.search(query, filters, limit, cursor, diverse)
        audit(self.db, p, 'search_photos', query[:200], {'count': len(result['results'])})
        return result

    def get(self, p: Principal, uid: str) -> dict:
        self._allow(p)
        row = self._row(uid)
        for key in ('metadata', 'evidence', 'keywords'):
            row[key] = loads(row[key], [] if key == 'keywords' else {})
        row['faces'] = [{**dict(r), 'box': loads(r['box']), 'evidence': loads(r['evidence'])} for r in self.db.q(
            'SELECT f.id,f.box,f.score,f.size_px,f.identity_id,f.assigned_by,f.evidence,i.name FROM photo_faces f LEFT JOIN identities i ON i.id=f.identity_id WHERE f.photo_id=?', (row['id'],))]
        for face in row['faces']:
            face['stale'] = bool(face['evidence'].get('revision') and face['evidence']['revision'] != row['revision'])
        row['variants'] = [dict(r) for r in self.db.q('SELECT uid,catalog_uid,lr_id,is_virtual,copy_name FROM photos WHERE asset_id=? AND deleted_at IS NULL', (row['asset_id'],))]
        row['rights'] = rights.get_rights(self.db, row['asset_id'])
        audit(self.db, p, 'get_photo', uid)
        return row

    def context(self, p: Principal, uid: str, families: list[str] | None = None) -> dict:
        self._allow(p)
        row = self._row(uid)
        if not row['catalog_uid']:
            connection = connection_details(self.bridge.status(), p.can('photos:edit'))
            row = self._link_existing(p, row, connection)
        if not row['catalog_uid']:
            revision = images.fingerprint(Path(row['path'])) if Path(row['path']).is_file() else ''
            can_import = bool(connection.get('can_edit') and revision)
            blocked_reason = 'The original file is unavailable and was not found in the open Lightroom catalogue. Reconnect the original or open its catalogue, then retry.' if not revision else connection['message']
            return {'photo_id': uid, 'revision': revision, 'import_on_edit': True,
                    'capabilities': {'editing': can_import, 'controls': {}, 'controls_after_import': True,
                                     'reason': 'Begin an edit to import this selected file in place and create a virtual copy; then read the copy’s context for its exact controls.' if can_import else blocked_reason},
                    'workflow': {'state': 'import_required' if can_import else 'blocked', 'connection': connection,
                                 'next_step': 'begin_photo_edits' if can_import else 'get_photo_workflow_status'},
                    'guidance': guidance(families), 'availability': row['availability']}
        result = self.bridge.call('mc_context', {'catalog_uid': row['catalog_uid'], 'photo_id': row['lr_id']})
        meta = result['photo']
        if result['catalog']['uid'] != row['catalog_uid']:
            raise PhotoConflict('The connected catalogue does not own this photograph')
        self.db.x('UPDATE photos SET revision=?,availability=?,updated_at=? WHERE id=?', (meta['revision'], meta.get('availability', row['availability']), now(), row['id']))
        audit(self.db, p, 'get_photo_edit_context', uid)
        return {'photo_id': uid, 'revision': meta['revision'], 'settings': meta.get('settings', {}),
                'availability': meta.get('availability'), 'capabilities': result['capabilities'],
                'workflow': {'state': 'ready' if result['capabilities'].get('editing') and p.can('photos:edit') else 'blocked',
                             'reason': result['capabilities'].get('reason') if p.can('photos:edit') else 'The agent token needs photos:edit.'},
                'process_version': meta.get('process_version'), 'recovery_snapshots': result.get('recovery_snapshots', []), 'guidance': guidance(families)}

    def preview(self, p: Principal, uid: str, edge: int = 1600, region: list[float] | None = None,
                native: bool = False, fresh: bool = False, expected_revision: str | None = None) -> tuple[bytes, dict]:
        self._allow(p)
        row = self._row(uid)
        self._media(p, row)
        # Folder ingestion should still discover Adobe's existing rendition.
        # This is a read-only catalogue lookup, not an import or a bulk sync.
        if not row['catalog_uid']:
            row = self._link_existing(p, row)
        edge = max(64, min(int(edge), 2048))
        if native and region is None:
            raise PhotoError('Request a detail region for native-resolution inspection')
        revision = row['revision']
        connected = True
        if row['catalog_uid']:
            try:
                current = self.context(p, uid)
                revision = current['revision']
                row['availability'] = current['availability']
            except LightroomUnavailable:
                connected = False
                if fresh or native:
                    raise
        else:
            revision = images.fingerprint(Path(row['path'])) if Path(row['path']).is_file() else row['revision']
        if expected_revision and expected_revision != revision:
            raise PhotoConflict('This preview no longer represents the requested develop revision')
        key = dumps([uid, revision, edge, region, native])
        data = None if fresh or native else self.cache.get(key)
        provenance = {'source': 'cached_rendition', 'native_resolution': False, 'colour_space': 'sRGB', 'dynamic_range': 'SDR', 'raw_recovery_known': False}
        if data:
            try:
                im = Image.open(io.BytesIO(data))
                im.load()
            except OSError:
                data = None
        if data is None:
            if row['catalog_uid'] and connected:
                args = {'catalog_uid': row['catalog_uid'], 'photo_id': row['lr_id']}
                if fresh or native:
                    if native and (not row['width'] or not row['height']):
                        raise PhotoError('Original dimensions are required to reserve a native-resolution render')
                    reserve = (int(row['width'])*int(row['height'])*4 if native else edge*edge*4) + 1024**2
                    with self.cache.scratch(reserve) as scratch:
                        result = self.bridge.call('mc_render', {**args, 'destination': str(scratch), 'expected_revision': revision, 'size': edge, 'native': native}, timeout=300)
                        path = Path(result['path']).resolve()
                        if not path.is_relative_to(scratch.resolve()) or not path.is_file() or path.stat().st_size > reserve:
                            raise PhotoError('Lightroom returned a rendition outside its reserved cache directory')
                        with Image.open(path) as opened:
                            im = opened.convert('RGB')
                        provenance = {**provenance, 'source': result.get('source', 'lightroom_render'), 'fresh_render': True,
                                      'native_resolution': bool(result.get('native_resolution'))}
                else:
                    result = self.bridge.call('mc_preview', {**args, 'size': min(edge, 1600)})
                    if result['revision'] != revision:
                        raise PhotoConflict('Lightroom changed while the preview was being requested')
                    im = Image.open(io.BytesIO(base64.b64decode(result['image']['data'], validate=True))).convert('RGB')
                    provenance = {**provenance, 'source': result.get('source', 'lightroom_preview'), 'fresh_render': False}
            elif row['catalog_uid']:
                raise LightroomUnavailable('This rendition is not cached. Open Lightroom to see the current edit; originals will not be substituted for edited previews.')
            else:
                im, provenance = images.decode(Path(row['path']), None if native else edge, native=native)
            provenance['source_width'], provenance['source_height'] = im.size
            if region is not None:
                im = images.region(im, region)
            scale = min(1., edge/max(im.size))
            provenance['native_resolution'] = bool(provenance.get('native_resolution')) and scale == 1
            provenance['pixel_scale'] = scale
            data = images.jpeg(im, edge)
            self.cache.put(key, data)
        with Image.open(io.BytesIO(data)) as out:
            width, height = out.size
        info = {'photo_id': uid, 'revision': revision, 'width': width, 'height': height,
                'region': region, 'coordinate_space': 'oriented_render', 'provenance': provenance}
        audit(self.db, p, 'get_photo_preview', uid, {'native': native, 'region': region, 'bytes': len(data)})
        return data, info

    def scan_folder(self, p: Principal, path: str, key: str) -> dict:
        self._allow(p, 'ingest:write')
        root = Path(path).expanduser().resolve()
        if not root.exists():
            raise PhotoError('Photo source does not exist on this computer')
        return self.jobs.enqueue(p, 'folder', {'path': str(root)}, key)

    def sync_catalog(self, p: Principal, key: str) -> dict:
        self._allow(p, 'ingest:write')
        state = self.bridge.call('mc_status')
        return self.jobs.enqueue(p, 'catalog', {'catalog_uid': state['catalog']['uid']}, key)

    def analyse_pending(self, p: Principal, key: str) -> dict:
        self._allow(p, 'ingest:write')
        return self.jobs.enqueue(p, 'analyse', {}, key)

    def install_models(self, p: Principal, key: str) -> dict:
        self._allow(p, 'admin')
        return self.jobs.enqueue(p, 'models', {}, key)

    def begin(self, p: Principal, photo_ids: list[str], expected_revisions: dict[str, str], key: str, brief: str = '', creative: bool = False) -> dict:
        self._allow(p, 'photos:edit')
        if not 1 <= len(photo_ids) <= 100 or len(set(photo_ids)) != len(photo_ids):
            raise PhotoError('Select 1 to 100 distinct photographs')
        if len(brief) > 4000 or type(creative) is not bool:
            raise PhotoError('Invalid editing brief or creative flag')
        for uid in photo_ids:
            self._media(p, self._row(uid))
            if not expected_revisions.get(uid):
                raise PhotoError('Read get_photo_edit_context for every photograph and provide its revision')
        return self.jobs.enqueue(p, 'begin', {'photo_ids': photo_ids, 'expected_revisions': expected_revisions, 'brief': brief, 'creative': creative}, key)

    def _session(self, p: Principal, uid: str) -> dict:
        row = self.db.q1('SELECT * FROM photo_edit_sessions WHERE uid=?', (uid,))
        if not row or (row['owner'] != p.username and not p.can('admin')):
            raise Forbidden('Edit session is not available to this caller')
        return dict(row)

    def apply(self, p: Principal, session_id: str, expected_revision: str, operations: list[dict], key: str) -> dict:
        self._allow(p, 'photos:edit')
        session = self._session(p, session_id)
        if session['status'] == 'finished':
            raise PhotoConflict('This editing session is finished; start a new session for further changes')
        # Validation and revision checks also happen at execution time. Do not
        # reject a completed idempotent replay solely because iterations moved.
        return self.jobs.enqueue(p, 'apply', {'session_id': session_id, 'expected_revision': expected_revision, 'operations': operations}, key)

    def finish(self, p: Principal, selections: list[dict], collection: str, key: str) -> dict:
        self._allow(p, 'photos:edit')
        require(p, 'collections:write')
        if not 1 <= len(selections) <= 100 or not collection.strip() or len(collection) > 200:
            raise PhotoError('Choose 1 to 100 edits and a collection name of 1 to 200 characters')
        if len({v['session_id'] for v in selections}) != len(selections):
            raise PhotoError('An edit session may appear only once')
        for item in selections:
            self._session(p, item['session_id'])
            if not item.get('reviewed_revision'):
                raise PhotoError('Each selection needs its visually reviewed revision')
        return self.jobs.enqueue(p, 'finish', {'selections': selections, 'collection': collection.strip()}, key)

    def restore(self, p: Principal, session_id: str, snapshot_id: str, expected_revision: str, key: str) -> dict:
        self._allow(p, 'photos:edit')
        self._session(p, session_id)
        return self.jobs.enqueue(p, 'restore', {'session_id': session_id, 'snapshot_id': snapshot_id, 'expected_revision': expected_revision}, key)

    def job(self, p: Principal, uid: str) -> dict:
        self._allow(p)
        job = self.jobs.get(uid)
        if job['owner'] != p.username and not p.can('admin'):
            raise Forbidden('Photo job is not available to this caller')
        return job

    def list_jobs(self, p: Principal) -> list[dict]:
        self._allow(p)
        rows = self.db.q('SELECT uid FROM photo_jobs'+('' if p.can('admin') else ' WHERE owner=?')+' ORDER BY created_at DESC LIMIT 50', () if p.can('admin') else (p.username,))
        return [self.jobs.get(r['uid']) for r in rows]

    def cancel(self, p: Principal, uid: str) -> dict:
        job = self.job(p, uid)
        self._allow(p, job_scope(job['kind']))
        self.db.x("UPDATE photo_jobs SET cancel_requested=1,status=CASE WHEN status IN ('queued','waiting') THEN 'cancelled' ELSE status END,updated_at=? WHERE uid=?", (now(), uid))
        return self.jobs.get(uid)

    def resume(self, p: Principal, uid: str) -> dict:
        job = self.job(p, uid)
        self._allow(p, job_scope(job['kind']))
        if job['status'] == 'conflict':
            raise PhotoConflict('Inspect the current edit and submit a new request with its revision')
        self.db.x("UPDATE photo_jobs SET status='queued',cancel_requested=0,error=NULL,updated_at=? WHERE uid=? AND status IN ('waiting','failed','cancelled')", (now(), uid))
        if self.jobs.autostart:
            self.jobs.start()
        return self.jobs.get(uid)

    def _actor(self, job: dict) -> tuple[Principal, dict]:
        request = loads(job['request'])
        actor = request['actor']
        scopes = set(actor['scopes']) & ROLE_SCOPES[actor['role']]
        if actor.get('token_id'):
            token = self.db.q1('SELECT t.scopes,t.revoked,t.expires_at,u.disabled,u.role FROM tokens t JOIN users u ON u.id=t.user_id WHERE t.id=?', (actor['token_id'],))
            if not token or token['revoked'] or token['disabled'] or (token['expires_at'] and token['expires_at'] < now()):
                raise Forbidden('The token authorising this job is no longer active')
            scopes &= set(loads(token['scopes'])) & ROLE_SCOPES[token['role']]
        p = Principal(actor['user_id'], actor['username'], actor['role'], scopes, 'system', actor.get('token_id'))
        self._allow(p, job_scope(job['kind']))
        return p, request['arguments']

    def execute(self, job: dict) -> dict:
        p, args = self._actor(job)
        handlers = {'folder': self._scan, 'catalog': self._sync, 'analyse': self._analyse, 'models': self._models,
                    'begin': self._begin, 'apply': self._apply, 'finish': self._finish, 'restore': self._restore}
        result = handlers[job['kind']](p, args, job)
        audit(self.db, p, 'photo_'+job['kind'], job['uid'], {'status': 'done'})
        return result

    def _models(self, p, args, job):
        installed = []
        for name in models.pack('photos'):
            self.jobs.checkpoint(job['uid'], {'models': installed, 'current_model': name})
            def progress(done, total):
                self.jobs.checkpoint(job['uid'], {'models': installed, 'current_model': name, 'downloaded_bytes': done, 'total_bytes': total})
            models.fetch(self.settings.resolved_models_dir, name, progress=lambda _: None, on_bytes=progress)
            installed.append(name)
        follow = self.jobs.enqueue(p, 'analyse', {}, job['uid']+'-analysis')
        return {'models': installed, 'analysis_job_id': follow['uid']}

    def _scan(self, p, args, job):
        root = Path(args['path'])
        stamp = now()
        with self.db.tx() as c:
            c.execute("INSERT OR IGNORE INTO sources(uri,kind,watch,created_at) VALUES(?,'photos',0,?)", (str(root), stamp))
            sid = c.execute('SELECT id FROM sources WHERE uri=?', (str(root),)).fetchone()['id']
        result = {'processed': 0, 'changed': 0, 'errors': []}
        for path in store.iter_photos(root):
            self.jobs.checkpoint(job['uid'])
            try:
                r = store.ingest_file(self.db, path, sid)
                result['changed'] += int(r['changed'])
            except (ValueError, OSError) as exc:
                if len(result['errors']) < 50:
                    result['errors'].append({'file': path.name, 'error': str(exc)})
            result['processed'] += 1
            if result['processed'] % 25 == 0:
                self.jobs.checkpoint(job['uid'], result)
        self.db.x('UPDATE sources SET last_scan=? WHERE id=?', (now(), sid))
        self.db.x("UPDATE photos SET availability='missing' WHERE catalog_uid IS NULL AND seen_at<? AND asset_id IN (SELECT id FROM assets WHERE source_id=?)", (stamp, sid))
        analysis_job = self.jobs.enqueue(p, 'analyse', {}, job['uid']+'-analysis')
        result['analysis_job_id'] = analysis_job['uid']
        return result

    def _sync(self, p, args, job):
        cursor, processed, stamp = 0, 0, now()
        while True:
            self.jobs.checkpoint(job['uid'])
            page = self.bridge.call('mc_catalog_page', {'catalog_uid': args['catalog_uid'], 'cursor': cursor, 'limit': 100})
            if page['catalog']['uid'] != args['catalog_uid']:
                raise PhotoConflict('Catalogue changed during synchronisation')
            store.catalog(self.db, page['catalog'])
            for photo in page['photos']:
                store.register(self.db, photo['path'], photo, catalog_uid=args['catalog_uid'])
                processed += 1
            next_cursor = int(page['cursor'])
            if next_cursor <= cursor and not page['complete']:
                raise PhotoError('Lightroom catalogue scan did not advance')
            cursor = next_cursor
            self.jobs.checkpoint(job['uid'], {'processed': processed, 'total': page['total'], 'cursor': cursor})
            if page['complete']:
                break
        self.db.x('UPDATE photo_catalogs SET last_sync=?,sync_cursor=? WHERE uid=?', (now(), cursor, args['catalog_uid']))
        self.db.x('UPDATE photos SET deleted_at=? WHERE catalog_uid=? AND seen_at<?', (now(), args['catalog_uid'], stamp))
        follow = self.jobs.enqueue(p, 'analyse', {}, job['uid']+'-analysis')
        return {'processed': processed, 'catalog_uid': args['catalog_uid'], 'analysis_job_id': follow['uid']}

    def _analyse(self, p, args, job):
        model_state = dumps({name: models.installed(self.settings.resolved_models_dir, name) for name in models.PHOTO_MODELS})
        progress = loads(job['result'], {})
        last_id, processed, unavailable = (progress.get(k, 0) for k in ('last_id', 'processed', 'unavailable'))
        while True:
            batch = self.db.q('SELECT uid,id FROM photos WHERE deleted_at IS NULL AND id>? ORDER BY id LIMIT 50', (last_id,))
            if not batch:
                break
            for entry in batch:
                self.jobs.checkpoint(job['uid'])
                row = self._row(entry['uid'])
                last_id = row['id']
                key = store.input_key(row, model_state)
                if row['analysis_key'] == key and row['status'] == 'ready':
                    continue
                started = time.monotonic()
                try:
                    data, info = self.preview(p, row['uid'], edge=1024)
                    evidence, vector, faces = analysis.analyse(Image.open(io.BytesIO(data)), self.settings, info['provenance'])
                    evidence['revision'] = info['revision']
                    self.db.x('UPDATE photos SET revision=? WHERE id=?', (info['revision'], row['id']))
                    key = store.input_key(self._row(row['uid']), model_state)
                    with self.db.tx() as c:
                        c.execute("UPDATE photos SET evidence=?,phash=?,analysis_key=?,status='ready',error=NULL,updated_at=? WHERE id=?", (dumps(evidence), evidence['phash'], key, now(), row['id']))
                        if vector is not None:
                            c.execute("INSERT INTO photo_vectors(photo_id,model,dim,vec,updated_at) VALUES(?,'siglip-base-multilingual',?,?,?) ON CONFLICT(photo_id) DO UPDATE SET model=excluded.model,dim=excluded.dim,vec=excluded.vec,updated_at=excluded.updated_at", (row['id'], len(vector), vector.astype(np.float16).tobytes(), now()))
                        c.execute("INSERT INTO photo_analysis_runs(photo_id,analyser,input_key,version,status,seconds,updated_at) VALUES(?,'visual',?,'1','done',?,?) ON CONFLICT(photo_id,analyser) DO UPDATE SET input_key=excluded.input_key,status='done',error=NULL,seconds=excluded.seconds,updated_at=excluded.updated_at", (row['id'], key, time.monotonic()-started, now()))
                        if evidence.get('models', {}).get('face_detection') == 'yunet':
                            for face in faces:
                                face['evidence']['revision'] = info['revision']
                            analysis.save_faces(self.db, row['id'], faces)
                        analysis.assign_burst(self.db, row, evidence['phash'])
                except LightroomUnavailable:
                    raise
                except Exception as exc:
                    unavailable += 1
                    self.db.x("UPDATE photos SET status='unavailable',error=?,updated_at=? WHERE id=?", (str(exc)[:1000], now(), row['id']))
                processed += 1
                self.jobs.checkpoint(job['uid'], {'processed': processed, 'unavailable': unavailable, 'last_id': last_id})
                if self.db.q1("SELECT 1 FROM photo_jobs WHERE status='queued' AND kind IN ('begin','apply','finish','restore') LIMIT 1"):
                    raise YieldToEdits()
        return {'processed': processed, 'unavailable': unavailable}

    def _record_lr_photo(self, catalog_uid: str, meta: dict) -> dict:
        return store.register(self.db, meta['path'], meta, catalog_uid=catalog_uid)

    def _begin(self, p, args, job):
        result = {'sessions': []}
        for uid in args['photo_ids']:
            self.jobs.checkpoint(job['uid'], result)
            row = self._row(uid)
            self._media(p, row)
            session_id = 'pe'+hashlib.sha256((job['uid']+uid).encode()).hexdigest()[:28]
            existing = self.db.q1('SELECT * FROM photo_edit_sessions WHERE uid=?', (session_id,))
            if existing and existing['status'] != 'creating':
                result['sessions'].append(self._session_result(dict(existing)))
                continue
            expected = existing['source_revision'] if existing else args['expected_revisions'][uid]
            if not row['catalog_uid']:
                if images.fingerprint(Path(row['path'])) != expected:
                    raise PhotoConflict('The original changed since it was inspected')
                state = self.bridge.call('mc_status')
                store.catalog(self.db, state['catalog'])
                imported = self.bridge.call('mc_import', {'catalog_uid': state['catalog']['uid'], 'path': row['path']})
                with self.db.tx():
                    self._record_lr_photo(state['catalog']['uid'], imported['photo'])
                    row = self._row(uid)
                    expected = imported['photo']['revision']
                    # Link the folder identity and its Lightroom baseline in
                    # one commit so a restart cannot mix their revision units.
                    self.db.x("INSERT OR IGNORE INTO photo_edit_sessions(uid,owner,source_photo_id,catalog_uid,source_revision,creative,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                              (session_id, p.username, row['id'], row['catalog_uid'], expected, int(args['creative']), args['brief'], now(), now()))
            self.db.x("INSERT OR IGNORE INTO photo_edit_sessions(uid,owner,source_photo_id,catalog_uid,source_revision,creative,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (session_id, p.username, row['id'], row['catalog_uid'], expected, int(args['creative']), args['brief'], now(), now()))
            made = self.bridge.call('mc_begin', {'catalog_uid': row['catalog_uid'], 'photo_id': row['lr_id'], 'expected_revision': expected, 'session_id': session_id}, timeout=300)
            target = self._record_lr_photo(row['catalog_uid'], made['photo'])
            self.db.x("UPDATE photo_edit_sessions SET target_photo_id=?,target_lr_id=?,revision=?,baseline_snapshot=?,updated_at=? WHERE uid=?",
                      (target['id'], made['photo']['lr_id'], made['photo']['revision'], made['baseline_snapshot'], now(), session_id))
            # Establish a genuine Lightroom baseline before editing.
            self.preview(p, target['uid'], fresh=True, expected_revision=made['photo']['revision'])
            self.db.x("UPDATE photo_edit_sessions SET status='active',updated_at=? WHERE uid=?", (now(), session_id))
            result['sessions'].append(self._session_result(self._session(p, session_id)))
        return result

    def _session_result(self, session: dict) -> dict:
        row = self.db.q1('SELECT uid FROM photos WHERE id=?', (session['target_photo_id'],))
        source = self.db.q1('SELECT uid FROM photos WHERE id=?', (session['source_photo_id'],))
        return {'session_id': session['uid'], 'photo_id': row['uid'] if row else None, 'source_photo_id': source['uid'],
                'revision': session['revision'], 'baseline_snapshot': session['baseline_snapshot'], 'best_snapshot': session['best_snapshot'],
                'iterations': session['iterations'], 'status': session['status']}

    def _target(self, p, session_id):
        session = self._session(p, session_id)
        target = self.db.q1('SELECT uid FROM photos WHERE id=?', (session['target_photo_id'],))
        if not target:
            raise PhotoError('The virtual copy has not been created yet')
        row = self._row(target['uid'])
        self._media(p, row)
        return session, row

    def _apply(self, p, args, job):
        session, row = self._target(p, args['session_id'])
        if session['status'] != 'active':
            raise PhotoConflict('Only an active, rendered edit session can be changed')
        prior = loads(job['result'], {})
        if not prior.get('applied'):
            if session['iterations'] >= 3:
                raise PhotoError('This session reached three refinement rounds. Inspect and finish or begin a new session.')
            context = self.context(p, row['uid'])
            # On a lost response the connector recognises operation_id before
            # checking expected_revision. Still validate shape/ranges locally.
            validate_operations(args['operations'], context['capabilities'], context['settings'], bool(session['creative']))
            changed = self.bridge.call('mc_apply', {'catalog_uid': session['catalog_uid'], 'photo_id': row['lr_id'],
                'session_id': session['uid'], 'expected_revision': args['expected_revision'], 'operations': args['operations'], 'operation_id': job['uid']}, timeout=300)
            self._record_lr_photo(session['catalog_uid'], changed['photo'])
            with self.db.tx() as c:
                c.execute('UPDATE photo_edit_sessions SET revision=?,best_snapshot=?,iterations=iterations+1,updated_at=? WHERE uid=?',
                          (changed['photo']['revision'], changed['snapshot_id'], now(), session['uid']))
                prior = {'applied': True, 'revision': changed['photo']['revision'], 'snapshot_id': changed['snapshot_id'],
                         'recovery_snapshot': changed.get('recovery_snapshot'), 'photo_id': row['uid']}
                c.execute('UPDATE photo_jobs SET result=?,updated_at=? WHERE uid=?', (dumps(prior), now(), job['uid']))
        self.jobs.checkpoint(job['uid'])
        data, info = self.preview(p, row['uid'], fresh=True, expected_revision=prior['revision'])
        evidence = analysis.measure(Image.open(io.BytesIO(data)), info['provenance'])
        return {**prior, 'session_id': session['uid'], 'preview': info, 'checks': evidence,
                'preview_url': f"/api/photos/{row['uid']}/preview?revision={prior['revision']}",
                'visual_review_required': True}

    def _restore(self, p, args, job):
        session, row = self._target(p, args['session_id'])
        if session['status'] != 'active':
            raise PhotoConflict('Start a new edit session before changing a finished copy')
        changed = self.bridge.call('mc_restore', {'catalog_uid': session['catalog_uid'], 'photo_id': row['lr_id'],
            'session_id': session['uid'], 'snapshot_id': args['snapshot_id'], 'expected_revision': args['expected_revision'], 'operation_id': job['uid']})
        self._record_lr_photo(session['catalog_uid'], changed['photo'])
        self.db.x('UPDATE photo_edit_sessions SET revision=?,updated_at=? WHERE uid=?', (changed['photo']['revision'], now(), session['uid']))
        _, info = self.preview(p, row['uid'], fresh=True, expected_revision=changed['photo']['revision'])
        return {'session_id': session['uid'], 'photo_id': row['uid'], 'revision': changed['photo']['revision'], 'preview': info}

    def _finish(self, p, args, job):
        require(p, 'collections:write')
        result = {'accepted': [], 'collection': args['collection']}
        with self.db.tx() as c:
            collection_uid = 'pc'+hashlib.sha256((p.username+'\0'+args['collection']).encode()).hexdigest()[:24]
            c.execute("INSERT OR IGNORE INTO collections(uid,name,kind,owner,created_at,updated_at) VALUES(?,?,'selects',?,?,?)", (collection_uid, args['collection'], p.username, now(), now()))
            collection = c.execute('SELECT id FROM collections WHERE uid=?', (collection_uid,)).fetchone()['id']
        for position, item in enumerate(args['selections']):
            self.jobs.checkpoint(job['uid'], result)
            session, row = self._target(p, item['session_id'])
            # A fresh rendition, not just a settings readback, must exist before
            # final delivery. User changes since visual review cause a conflict.
            self.preview(p, row['uid'], fresh=True, expected_revision=item['reviewed_revision'])
            saved = self.bridge.call('mc_finish', {'catalog_uid': session['catalog_uid'], 'photo_id': row['lr_id'],
                'session_id': session['uid'], 'expected_revision': item['reviewed_revision'], 'collection': args['collection'],
                'operation_id': job['uid']+'-'+session['uid']})
            self.db.x("UPDATE photo_edit_sessions SET status='finished',updated_at=? WHERE uid=?", (now(), session['uid']))
            self.db.x('INSERT OR IGNORE INTO photo_collection_items(collection_id,photo_id,position,added_at) VALUES(?,?,?,?)', (collection, row['id'], position, now()))
            result['accepted'].append({'photo_id': row['uid'], 'session_id': session['uid'], 'lightroom_collection_id': saved['collection_id']})
        result['collection_uid'] = collection_uid
        return result

    def name_face(self, p: Principal, face_id: int, name: str) -> dict:
        self._allow(p, 'tags:write')
        if p.is_agent:
            raise Forbidden('Naming people is a decision for a person, not an agent')
        if not name.strip() or len(name) > 100:
            raise PhotoError('Person name must contain 1 to 100 characters')
        row = self.db.q1('SELECT identity_id FROM photo_faces WHERE id=?', (face_id,))
        if not row or not row['identity_id']:
            raise PhotoError('This face has no usable identity embedding')
        from ..people import rename
        rename(self.db, row['identity_id'], name.strip(), p.username)
        self.db.x("UPDATE photo_faces SET assigned_by='human' WHERE id=?", (face_id,))
        audit(self.db, p, 'name_photo_face', str(face_id), {'name': name.strip()})
        return {'identity_id': row['identity_id'], 'name': name.strip()}

    def move_face(self, p: Principal, face_id: int, identity_id: int | None) -> dict:
        self._allow(p, 'tags:write')
        if p.is_agent:
            raise Forbidden('Grouping people is a decision for a person, not an agent')
        from ..people import _recompute
        with self.db.tx() as c:
            row = c.execute('SELECT identity_id,embedding,photo_id FROM photo_faces WHERE id=?', (face_id,)).fetchone()
            if not row or not row['embedding']:
                raise PhotoError('This face has no usable identity embedding')
            if identity_id is None:
                emb = np.frombuffer(row['embedding'], np.float16).astype(np.float32)
                identity_id = c.execute('INSERT INTO identities(centroid,n,created_at,updated_at) VALUES(?,1,?,?)', (emb.tobytes(), now(), now())).lastrowid
            elif not c.execute('SELECT 1 FROM identities WHERE id=?', (identity_id,)).fetchone():
                raise PhotoError('Person not found')
            current = np.frombuffer(row['embedding'], np.float16).astype(np.float32)
            for label in c.execute('SELECT identity_id,embedding FROM photo_face_labels WHERE photo_id=?', (row['photo_id'],)).fetchall():
                if float(np.frombuffer(label['embedding'], np.float16).astype(np.float32) @ current) >= .5:
                    c.execute('DELETE FROM photo_face_labels WHERE photo_id=? AND identity_id=?', (row['photo_id'], label['identity_id']))
            c.execute("UPDATE photo_faces SET identity_id=?,assigned_by='human' WHERE id=?", (identity_id, face_id))
            _recompute(c, identity_id)
            if row['identity_id']:
                _recompute(c, row['identity_id'])
        audit(self.db, p, 'move_photo_face', str(face_id), {'identity_id': identity_id})
        return {'face_id': face_id, 'identity_id': identity_id}

    def feedback(self, p: Principal, uid: str, favourite: bool | None, note: str = '') -> dict:
        self._allow(p, 'tags:write')
        row = self._row(uid)
        if (favourite is not None and type(favourite) is not bool) or len(note) > 2000:
            raise PhotoError('Invalid favourite or note')
        self.db.x('INSERT INTO photo_feedback(photo_id,favourite,note,updated_at) VALUES(?,?,?,?) ON CONFLICT(photo_id) DO UPDATE SET favourite=excluded.favourite,note=excluded.note,updated_at=excluded.updated_at', (row['id'], favourite, note, now()))
        return {'photo_id': uid, 'favourite': favourite, 'note': note}
