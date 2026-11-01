from pathlib import Path

from metachlorian.auth import LOCAL_ADMIN
from metachlorian.db import Database
from metachlorian.ingest import scan
from metachlorian.jobs import queue
from metachlorian.service import Library


def test_remove_folder_and_rescan_parent_preserves_originals_and_siblings(lib, tmp_path):
    settings, db = lib
    root = tmp_path / 'footage'
    folder = root / '2025-11-09'
    nested = folder / 'nested'
    sibling = root / '2025-11-09-extra'
    nested.mkdir(parents=True)
    sibling.mkdir()
    files = [folder / 'one.mp4', nested / 'two.mov', sibling / 'keep.mp4']
    for n, path in enumerate(files):
        path.write_bytes(str(n).encode())
    sid = scan.add_source(db, str(root))
    scan.scan_source(db, sid)
    removed_id = db.q1('SELECT asset_id FROM asset_paths WHERE path=?', (str(files[0]),))[0]
    queue.enqueue(db, removed_id, 'technical', 'test', 0)
    queue.claim(db, 'worker')  # Even a running lease must be removed.
    service = Library(db, settings)
    result = service.exclude_folder(LOCAL_ADMIN, str(folder))
    assert result['removed'] == 2
    assert all(p.exists() for p in files)
    assert db.q1('SELECT COUNT(*) FROM jobs WHERE asset_id=?', (removed_id,))[0] == 0
    reopened = Database(settings.db_path)
    assert scan.excluded_folders(reopened) == [str(folder.resolve())]
    scanned = scan.scan_source(reopened, sid)
    assert scanned.unchanged == 1 and scanned.added == scanned.changed == 0
    assert scan.scan_status(reopened, sid)['found'] == 1
    assert db.q1('SELECT COUNT(*) FROM assets WHERE deleted_at IS NULL')[0] == 1
    assert scan.register_file(reopened, files[0]) == ('excluded', None)
    assert list(scan.iter_videos(folder, excluded=scan.excluded_folders(reopened))) == []
    assert service.exclude_folder(LOCAL_ADMIN, str(folder))['removed'] == 0
    reopened.close()


def test_exclusion_during_hash_cannot_restore_asset(lib, tmp_path, monkeypatch):
    settings, db = lib
    folder = tmp_path / 'footage'
    folder.mkdir()
    video = folder / 'one.mp4'
    video.write_bytes(b'video')
    original_hash = scan.content_hash

    def hashing(path):
        Library(db, settings).exclude_folder(LOCAL_ADMIN, str(folder))
        return original_hash(path)

    monkeypatch.setattr(scan, 'content_hash', hashing)
    assert scan.register_file(db, video) == ('excluded', None)
    assert db.q1('SELECT COUNT(*) FROM assets')[0] == 0


def test_exclusion_during_discovered_scan_skips_pending_files(lib, tmp_path):
    settings, db = lib
    folder = tmp_path / 'footage'
    folder.mkdir()
    for n in range(3):
        (folder / f'{n}.mp4').write_bytes(str(n).encode())
    sid = scan.add_source(db, str(folder))
    result = scan.scan_source(db, sid, on_asset=lambda aid: Library(db, settings).exclude_folder(LOCAL_ADMIN, str(folder)))
    assert result.added == 1 and result.excluded == 2
    assert scan.scan_status(db, sid)['errors'] == 0
    assert db.q1('SELECT COUNT(*) FROM assets WHERE deleted_at IS NULL')[0] == 0
    assert db.q1('SELECT watch FROM sources WHERE id=?', (sid,))[0] == 0


def test_windows_folder_boundary_and_case():
    if __import__('os').name == 'nt':
        assert scan.path_within('d:/PHOTOS/2025-11-09/one.mp4', 'D:\\Photos\\2025-11-09')
        assert not scan.path_within('D:/Photos/2025-11-09-extra/one.mp4', 'D:/Photos/2025-11-09')
