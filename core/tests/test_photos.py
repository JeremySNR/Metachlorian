"""Photo workflow contracts. Fake Lightroom verifies orchestration, not Adobe rendering."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image, ImageEnhance

from metachlorian.auth import LOCAL_ADMIN, Principal, Forbidden
from metachlorian.config import load_settings
from metachlorian.db import Database, MIGRATIONS, _split_sql, now
from metachlorian.photos import store
from metachlorian.photos.cache import PreviewCache
from metachlorian.photos.controls import CONTROLS, validate_operations
from metachlorian.photos.errors import CacheBudgetExceeded, LightroomUnavailable, PhotoConflict
from metachlorian.photos.images import decode, jpeg, region
from metachlorian.photos.service import PhotoLibrary


class FakeLightroom:
    def __init__(self, root):
        self.catalog = {'uid': 'cat-family', 'path': str(root/'Family.lrcat'), 'name': 'Family', 'version': '15.6'}
        self.photos, self.snapshots, self.receipts, self.copies, self.collections = {}, {}, {}, {}, {}
        self.online, self.lose_response = True, False
        self.apply_count = 0
        path = root/'family.jpg'
        im = Image.new('RGB', (120, 80), (90, 110, 140))
        for x in range(20, 80):
            for y in range(10, 60):
                im.putpixel((x, y), (150 + x % 20, 80 + y, 40))
        im.save(path)
        self.photos['1'] = {'lr_id': '1', 'path': str(path), 'filename': path.name, 'keywords': ['Family', 'Holiday'],
                            'capture_time': '2026-07-12T10:00:00', 'cameraModel': 'Camera', 'dimensions': {'width': 120, 'height': 80},
                            'last_edit_time': 1, 'is_virtual': False, 'availability': 'original',
                            'settings': {'Exposure2012': 0., 'Temperature': 5500., 'Tint': 0., 'CropLeft': 0., 'CropRight': 1., 'CropTop': 0., 'CropBottom': 1.}}

    def meta(self, uid):
        data = copy.deepcopy(self.photos[uid])
        data['revision'] = hashlib.sha256(json.dumps(data['settings'], sort_keys=True).encode()).hexdigest()
        return data

    def status(self):
        return {'connected': self.online, 'catalog': self.catalog}

    def close(self):
        pass

    def call(self, action, args=None, **kwargs):
        if not self.online:
            raise LightroomUnavailable('Lightroom is offline')
        args = args or {}
        if action == 'mc_status':
            return {'catalog': self.catalog, 'protocol': 1}
        if args.get('catalog_uid') != self.catalog['uid']:
            raise PhotoConflict('Wrong catalogue')
        if action == 'mc_catalog_page':
            return {'catalog': self.catalog, 'photos': [self.meta(k) for k in self.photos], 'cursor': len(self.photos), 'total': len(self.photos), 'complete': True}
        uid = str(args.get('photo_id', '1'))
        if action == 'mc_import':
            return {'catalog': self.catalog, 'photo': self.meta('1')}
        if action == 'mc_context':
            return {'catalog': self.catalog, 'photo': self.meta(uid), 'capabilities': {'controls': CONTROLS, 'mask_types': ['subject','sky','background'], 'auto': True}}
        if action in {'mc_preview', 'mc_render'}:
            im = Image.open(self.photos[uid]['path']).convert('RGB')
            im = ImageEnhance.Brightness(im).enhance(2**self.photos[uid]['settings']['Exposure2012'])
            if action == 'mc_preview':
                return {'image': {'data': base64.b64encode(jpeg(im)).decode()}, 'revision': self.meta(uid)['revision'], 'source': 'lightroom_preview'}
            self._check(uid, args)
            path = Path(args['destination'])/'render.jpg'
            im.save(path)
            return {'path': str(path), 'revision': self.meta(uid)['revision'], 'source': 'original', 'native_resolution': bool(args.get('native'))}
        if action == 'mc_begin':
            if args['session_id'] not in self.copies:
                self._check(uid, args)
                target = str(len(self.photos)+1)
                self.photos[target] = {**copy.deepcopy(self.photos[uid]), 'lr_id': target, 'is_virtual': True, 'master_lr_id': uid, 'copy_name': 'Metachlorian '+args['session_id']}
                self.copies[args['session_id']] = target
                self.snapshots['baseline-'+target] = copy.deepcopy(self.photos[target]['settings'])
            target = self.copies[args['session_id']]
            return {'photo': self.meta(target), 'baseline_snapshot': 'baseline-'+target}
        operation = args['operation_id']
        if operation in self.receipts:
            return copy.deepcopy(self.receipts[operation])
        self._check(uid, args)
        if uid not in self.copies.values():
            raise ValueError('Refusing to edit a master')
        if action == 'mc_apply':
            self.apply_count += 1
            for op in args['operations']:
                if op['op'] == 'settings':
                    self.photos[uid]['settings'].update(op['values'])
            snap = 'snapshot-'+operation
            self.snapshots[snap] = copy.deepcopy(self.photos[uid]['settings'])
            result = {'photo': self.meta(uid), 'snapshot_id': snap, 'recovery_snapshot': 'baseline-'+uid}
        elif action == 'mc_restore':
            self.photos[uid]['settings'] = copy.deepcopy(self.snapshots[args['snapshot_id']])
            result = {'photo': self.meta(uid)}
        elif action == 'mc_finish':
            self.collections.setdefault(args['collection'], set()).add(uid)
            result = {'collection_id': 'selection-1', 'photo': self.meta(uid)}
        else:
            raise AssertionError(action)
        self.receipts[operation] = result
        if self.lose_response and action == 'mc_apply':
            self.lose_response = False
            raise LightroomUnavailable('Response lost after apply')
        return copy.deepcopy(result)

    def _check(self, uid, args):
        if self.meta(uid)['revision'] != args['expected_revision']:
            raise PhotoConflict('Develop state changed')


@pytest.fixture
def photos(tmp_path):
    settings = load_settings(tmp_path/'library', photos_enabled=True, workers=0)
    settings.ensure_dirs()
    db = Database(settings.db_path)
    bridge = FakeLightroom(tmp_path)
    service = PhotoLibrary(db, settings, bridge)
    service.jobs.autostart = False
    store.catalog(db, bridge.catalog)
    registered = store.register(db, bridge.photos['1']['path'], bridge.meta('1'), catalog_uid=bridge.catalog['uid'])
    yield service, bridge, registered['uid']
    db.close()


def run(service, job):
    assert service.jobs.run_once()
    return service.job(LOCAL_ADMIN, job['uid'])


def begin(service, uid):
    ctx = service.context(LOCAL_ADMIN, uid)
    job = service.begin(LOCAL_ADMIN, [uid], {uid: ctx['revision']}, 'begin-test', 'Natural family photographs')
    result = run(service, job)
    assert result['status'] == 'done', result
    return result['result']['sessions'][0]


def test_migration_preserves_video_children(tmp_path):
    path = tmp_path/'old.sqlite'
    c = sqlite3.connect(path)
    for script in MIGRATIONS[:7]:
        for stmt in _split_sql(script):
            c.execute(stmt)
    c.execute("INSERT INTO meta VALUES('schema_version','7')")
    c.execute("INSERT INTO assets(id,uid,path,filename,size,mtime,quick_hash,created_at,updated_at) VALUES(1,'video','/clip.mp4','clip.mp4',100,1,'hash',1,1)")
    c.execute("INSERT INTO shots(id,uid,asset_id,idx,start_s,end_s,start_frame,end_frame,segmenter) VALUES(1,'shot',1,0,0,1,0,24,'fixture')")
    c.commit()
    c.close()
    db = Database(path)
    assert db.get_meta('schema_version') == '8'
    assert db.q1('SELECT media_kind FROM assets')[0] == 'video'
    assert db.q1('SELECT asset_id FROM shots')[0] == 1
    assert not db.q('PRAGMA foreign_key_check')
    assert db.q1('PRAGMA foreign_keys')[0] == 1


def test_offline_catalogue_and_variant_identity(photos, tmp_path):
    service, bridge, uid = photos
    meta = {**bridge.meta('1'), 'lr_id': '99', 'path': str(tmp_path/'missing.CR3'), 'availability': 'smart_preview'}
    a = store.register(service.db, meta['path'], meta, catalog_uid=bridge.catalog['uid'])
    b = store.register(service.db, meta['path'], meta, catalog_uid=bridge.catalog['uid'])
    assert a['uid'] == b['uid']
    row = service._row(a['uid'])
    assert row['size'] is None and row['availability'] == 'smart_preview'
    copy_meta = {**meta, 'lr_id': '100', 'is_virtual': True, 'master_lr_id': '99'}
    other = store.register(service.db, meta['path'], copy_meta, catalog_uid=bridge.catalog['uid'])
    assert other['uid'] != a['uid'] and other['asset_id'] == a['asset_id']
    assert not service.db.q('SELECT * FROM shots')


def test_complete_edit_loop_and_retry(photos):
    service, bridge, uid = photos
    original = Path(bridge.photos['1']['path']).read_bytes()
    selected = service.search(LOCAL_ADMIN, 'Holiday', diverse=False)
    assert selected['results'][0]['uid'] == uid
    session = begin(service, uid)
    args = (LOCAL_ADMIN, session['session_id'], session['revision'], [{'op':'settings', 'values':{'Exposure2012': .35}}], 'apply-test')
    job = service.apply(*args)
    result = run(service, job)
    assert result['status'] == 'done', result
    assert service.apply(*args)['uid'] == job['uid']
    assert bridge.apply_count == 1
    data, info = service.preview(LOCAL_ADMIN, session['photo_id'])
    assert data.startswith(b'\xff\xd8') and info['revision'] == result['result']['revision']
    delivered = run(service, service.finish(LOCAL_ADMIN, [{'session_id':session['session_id'], 'reviewed_revision':info['revision']}], 'Holiday favourites', 'finish-test'))
    assert delivered['status'] == 'done', delivered
    assert len(bridge.collections['Holiday favourites']) == 1
    assert Path(bridge.photos['1']['path']).read_bytes() == original
    assert bridge.photos['1']['settings']['Exposure2012'] == 0
    assert service.db.q1('SELECT COUNT(*) FROM photo_collection_items')[0] == 1


def test_lost_response_reconciles_without_reapplying(photos):
    service, bridge, uid = photos
    session = begin(service, uid)
    bridge.lose_response = True
    job = service.apply(LOCAL_ADMIN, session['session_id'], session['revision'], [{'op':'settings','values':{'Exposure2012': .2}}], 'lost-response')
    assert run(service, job)['status'] == 'waiting'
    service.resume(LOCAL_ADMIN, job['uid'])
    result = run(service, job)
    assert result['status'] == 'done', result
    assert bridge.apply_count == 1
    assert service._session(LOCAL_ADMIN, session['session_id'])['iterations'] == 1


def test_human_change_conflicts_and_no_stale_delivery(photos):
    service, bridge, uid = photos
    session = begin(service, uid)
    bridge.photos['2']['settings']['Exposure2012'] = 1
    job = service.apply(LOCAL_ADMIN, session['session_id'], session['revision'], [{'op':'settings','values':{'Exposure2012': .2}}], 'human-race')
    result = run(service, job)
    assert result['status'] == 'conflict', result
    assert bridge.apply_count == 0
    with pytest.raises(PhotoConflict):
        service.preview(LOCAL_ADMIN, session['photo_id'], expected_revision=session['revision'])


def test_scope_owner_and_idempotency(photos):
    service, bridge, uid = photos
    reader = Principal(10, 'reader', 'agent', {'library:read'})
    with pytest.raises(Forbidden):
        service.begin(reader, [uid], {uid:'revision'}, 'no-scope')
    job = service.scan_folder(LOCAL_ADMIN, str(Path(bridge.photos['1']['path']).parent), 'key')
    with pytest.raises(PhotoConflict):
        service.jobs.enqueue(LOCAL_ADMIN, 'folder', {'path':'different'}, 'key')
    with pytest.raises(Forbidden):
        service.job(reader, job['uid'])


def test_control_validation():
    caps = {'controls':CONTROLS, 'mask_types':['subject'], 'auto':True}
    with pytest.raises(ValueError):
        validate_operations([{'op':'settings','values':{'ProcessVersion':'15.4'}}], caps, {})
    with pytest.raises(ValueError):
        validate_operations([{'op':'settings','values':{'Exposure2012':float('nan')}}], caps, {})
    with pytest.raises(ValueError):
        validate_operations([{'op':'settings','values':{'CropLeft':.8,'CropRight':.3}}], caps, {})
    with pytest.raises(ValueError):
        validate_operations([{'op':'settings','values':{'ToneCurvePV2012':[0,0,200,180,100,255]}}], caps, {})
    with pytest.raises(ValueError):
        validate_operations([{'op':'mask','type':'people','adjustments':{'local_Exposure':.1}}], caps, {})
    for values in ({'LensProfileEnable': .5}, {'AutoLateralCA': True}, {'PerspectiveUpright': 5}):
        with pytest.raises(ValueError):
            validate_operations([{'op': 'settings', 'values': values}], caps, {})


def test_cache_budget_and_crash_cleanup(tmp_path):
    cache = PreviewCache(tmp_path/'cache', 100)
    cache.put('a', b'x'*60)
    cache.put('b', b'x'*60)
    assert cache.stats()['bytes'] == 60 and cache.get('a') is None
    with pytest.raises(CacheBudgetExceeded):
        with cache.scratch(101):
            pass
    with pytest.raises(RuntimeError):
        with cache.scratch(80) as scratch:
            (scratch/'render.jpg').write_bytes(b'x'*70)
            raise RuntimeError('crash')
    assert not list(cache.root.glob('scratch-*'))
    assert cache.stats()['bytes'] <= 100


@pytest.mark.parametrize('orientation', range(1, 9))
def test_orientations_preserve_frame(tmp_path, orientation):
    im = Image.new('RGB', (60, 30), 'red')
    exif = Image.Exif()
    exif[274] = orientation
    path = tmp_path/f'{orientation}.jpg'
    im.save(path, exif=exif)
    decoded, info = decode(path, native=True)
    assert decoded.size == ((30,60) if orientation in {5,6,7,8} else (60,30))
    assert info['native_resolution']
    assert region(decoded, [0,0,.5,.5]).width == decoded.width//2
