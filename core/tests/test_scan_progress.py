from pathlib import Path

import pytest

from metachlorian.auth import LOCAL_ADMIN
from metachlorian.db import Database
from metachlorian.ingest import scan
from metachlorian.service import Library


def test_nested_scan_progress_dedupe_and_incremental_planning(lib, tmp_path):
    settings, db = lib
    root = tmp_path / 'footage'
    nested = root / 'year' / 'day'
    nested.mkdir(parents=True)
    (root / 'one.MP4').write_bytes(b'one')
    (nested / 'two.mov').write_bytes(b'two')
    (nested / 'copy.mp4').write_bytes(b'one')
    (nested / 'photo.jpg').write_bytes(b'photo')
    sid = scan.add_source(db, str(root))
    callbacks = []

    def planned(aid):
        progress = scan.scan_status(db, sid)
        callbacks.append((aid, progress['state'], progress['processed']))

    result = scan.scan_source(db, sid, on_asset=planned)
    assert result.added == 2 and result.duplicates == 1
    assert len(callbacks) == 3
    assert callbacks[0][1:] == ('registering', 0)
    progress = scan.scan_status(db, sid)
    assert progress['state'] == 'completed'
    assert progress['directories'] == 3
    assert progress['found'] == progress['processed'] == 3
    assert progress['errors'] == 0
    reopened = Database(settings.db_path)
    assert scan.scan_status(reopened, sid) == progress
    reopened.close()
    callbacks.clear()
    scan.scan_source(db, sid, on_asset=planned)
    assert len(callbacks) == 3  # recover registration interrupted before planning


def test_offline_source_does_not_mark_saved_files_missing(lib, tmp_path):
    _, db = lib
    root = tmp_path / 'drive'
    root.mkdir()
    (root / 'one.mp4').write_bytes(b'one')
    sid = scan.add_source(db, str(root))
    scan.scan_source(db, sid)
    previous_scan = db.q1('SELECT last_scan FROM sources')[0]
    root.rename(tmp_path / 'unplugged')
    with pytest.raises(FileNotFoundError):
        scan.scan_source(db, sid)
    assert scan.scan_status(db, sid)['state'] == 'failed'
    assert db.q1('SELECT status FROM assets')[0] == 'new'
    assert db.q1('SELECT COUNT(*) FROM asset_paths')[0] == 1
    assert db.q1('SELECT last_scan FROM sources')[0] == previous_scan


def test_read_error_reported_and_scan_continues(lib, tmp_path, monkeypatch):
    _, db = lib
    (tmp_path / 'bad.mp4').write_bytes(b'bad')
    (tmp_path / 'good.mp4').write_bytes(b'good')
    sid = scan.add_source(db, str(tmp_path))
    original = scan.register_file

    def register(db, path, *args, **kwargs):
        if Path(path).name == 'bad.mp4':
            raise PermissionError('Access denied')
        return original(db, path, *args, **kwargs)

    monkeypatch.setattr(scan, 'register_file', register)
    scan.scan_source(db, sid)
    progress = scan.scan_status(db, sid)
    assert progress['state'] == 'completed_with_errors'
    assert progress['found'] == progress['processed'] == 2
    assert progress['errors'] == 1 and progress['added'] == 1
    assert 'bad.mp4' in progress['issues'][0]


def test_directory_error_is_not_silently_complete(lib, tmp_path, monkeypatch):
    _, db = lib
    sid = scan.add_source(db, str(tmp_path))

    def walk(root, onerror):
        onerror(PermissionError('Cannot read private subfolder'))
        yield str(root), [], []

    monkeypatch.setattr(scan.os, 'walk', walk)
    scan.scan_source(db, sid)
    assert scan.scan_status(db, sid)['state'] == 'completed_with_errors'


def test_duplicate_scan_requests_and_running_scan_are_coalesced(lib, tmp_path):
    _, db = lib
    sid = scan.add_source(db, str(tmp_path))
    assert scan.queue_scan(db, sid)
    assert not scan.queue_scan(db, sid)
    with scan.scan_lock(db, sid):
        assert not scan.queue_scan(db, sid)
        assert scan.scan_source(db, sid).added == 0
    scan.scan_source(db, sid)
    assert scan.queue_scan(db, sid)


def test_source_api_returns_queued_scan_and_persists_result(lib, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from metachlorian.api.app import create_app
    from metachlorian import pipeline

    settings, db = lib
    (tmp_path / 'clip.mp4').write_bytes(b'clip')
    planned = []
    monkeypatch.setattr(pipeline, 'plan_asset', lambda db, settings, aid: planned.append(aid))
    client = TestClient(create_app(settings, db, start_workers=False), base_url='http://127.0.0.1', client=('127.0.0.1', 50000))
    response = client.post('/api/sources', json={'uri': str(tmp_path)}, headers={'X-Metachlorian': '1'})
    assert response.status_code == 200, response.text
    assert response.json()['scan']['state'] == 'queued'
    assert len(planned) == 1
    source = client.get('/api/sources').json()['sources'][0]
    assert source['scan']['state'] == 'completed'
    assert source['scan']['found'] == 1


def test_processing_pagination_keeps_older_imports_findable(lib):
    settings, db = lib
    with db.tx() as c:
        c.executemany('INSERT INTO assets(uid,path,filename,size,mtime,quick_hash,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                      [(f'a{i}', f'/yesterday/{i}.mp4', f'{i}.mp4', 1, 0, str(i), 'ready', 0, 0) for i in range(205)])
    service = Library(db, settings)
    first = service.processing(LOCAL_ADMIN)
    second = service.processing(LOCAL_ADMIN, offset=200)
    assert first['total'] == second['total'] == 205
    assert len(first['assets']) == 200 and len(second['assets']) == 5
    assert len({a['uid'] for a in first['assets'] + second['assets']}) == 205
    assert service.processing(LOCAL_ADMIN, q='0.mp4')['total'] == 21
    assert service.processing(LOCAL_ADMIN, q='yesterday')['total'] == 205
    assert first['library_path'] == str(settings.data_dir)


def test_runtime_resumes_interrupted_non_watched_scan(lib, tmp_path, monkeypatch):
    import threading
    from metachlorian import pipeline, runtime
    from metachlorian.db import dumps

    settings, db = lib
    root = tmp_path / 'once'
    root.mkdir()
    path = root / 'clip.mp4'
    path.write_bytes(b'clip')
    sid = scan.add_source(db, str(root), watch=False)
    _, aid = scan.register_file(db, path, sid)
    db.set_meta(f'scan:{sid}', dumps({'state': 'registering'}))
    stop = threading.Event()
    planned = []
    monkeypatch.setattr(pipeline, 'plan_asset', lambda db, settings, asset_id: planned.append(asset_id))
    monkeypatch.setattr(pipeline, 'plan_all', lambda *args: stop.set())
    runtime._watch(settings, stop)
    assert planned == [aid]
    assert scan.scan_status(db, sid)['state'] == 'completed'


def test_sprites_encode_limited_range_video_as_full_range_jpeg(sample_video, tmp_path):
    from metachlorian.media.ffmpeg import make_sprites
    from PIL import Image

    result = make_sprites(sample_video, tmp_path / 'sprites', duration=6, cols=3, rows=2)
    assert result.count == 6 and len(result.sheets) == 1
    with Image.open(tmp_path / 'sprites' / result.sheets[0]) as image:
        assert image.size == (result.tile_w * 3, result.tile_h * 2)


def test_reappearing_duplicate_restores_missing_asset(lib, tmp_path):
    _, db = lib
    root = tmp_path / 'footage'
    root.mkdir()
    path = root / 'clip.mp4'
    path.write_bytes(b'clip')
    sid = scan.add_source(db, str(root))
    scan.scan_source(db, sid)
    path.unlink()
    scan.scan_source(db, sid)
    assert db.q1('SELECT status FROM assets')[0] == 'missing'
    path.write_bytes(b'clip')
    result = scan.scan_source(db, sid)
    assert result.duplicates == 1
    assert db.q1('SELECT status FROM assets')[0] != 'missing'
    assert db.q1('SELECT COUNT(*) FROM assets')[0] == 1


def test_simultaneous_upload_and_folder_copy_share_one_asset(lib, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    settings, db = lib
    paths = [tmp_path / 'upload.mp4', tmp_path / 'folder-copy.mp4']
    for path in paths:
        path.write_bytes(b'identical footage')
    barrier = Barrier(2)
    original = scan.content_hash
    def hash_together(path):
        digest = original(path)
        barrier.wait(timeout=5)
        return digest
    monkeypatch.setattr(scan, 'content_hash', hash_together)
    def register(path):
        connection = Database(settings.db_path)
        try:
            return scan.register_file(connection, path)
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, paths))
    assert sorted(outcome for outcome, _ in results) == ['added', 'duplicate']
    assert results[0][1] == results[1][1]
    assert db.q1('SELECT COUNT(*) FROM assets')[0] == 1
    assert db.q1('SELECT COUNT(*) FROM asset_paths')[0] == 2
