import pytest

from metachlorian.auth import LOCAL_ADMIN
from metachlorian.db import dumps
from metachlorian.ingest.scan import register_file
from metachlorian.service import Library


def test_files_page_all_unprocessed_assets_in_capture_order(lib, tmp_path):
    settings, db = lib
    for n in range(125):
        path = tmp_path / f'{n}.mp4'
        path.write_bytes(str(n).encode())
        _, aid = register_file(db, path)
        # Import order is the reverse of capture order, and some dates are absent.
        captured = f'2025-{12 - n // 28:02d}-{28 - n % 28:02d}T12:00:00Z' if n < 120 else None
        if captured and n % 2 == 0:
            captured = captured[:10].replace('-', ':') + ' 12:00:00+00:00'
        if n == 124:
            captured = '0000:00:00 00:00:00'
        db.x('UPDATE assets SET tech=? WHERE id=?', (dumps({'capture_date': captured}), aid))
    service = Library(db, settings)
    pages = [service.list_assets(LOCAL_ADMIN, sort='captured_desc', limit=60, offset=i) for i in (0, 60, 120)]
    assert [len(p['assets']) for p in pages] == [60, 60, 5]
    assert all(p['total'] == 125 for p in pages)
    assets = [a for p in pages for a in p['assets']]
    assert len({a['uid'] for a in assets}) == 125
    assert assets[0]['filename'] == '0.mp4'
    assert assets[119]['filename'] == '119.mp4'
    assert all(a['captured'] is None for a in assets[120:])
    assert all(not a['preview_ready'] for a in assets)
    oldest = service.list_assets(LOCAL_ADMIN, sort='captured_asc', limit=500)['assets']
    assert oldest[0]['filename'] == '119.mp4'
    assert all(a['captured'] is None for a in oldest[120:])
    assert service.list_assets(LOCAL_ADMIN)['assets'][0]['filename'] == '124.mp4'
    with pytest.raises(ValueError):
        service.list_assets(LOCAL_ADMIN, sort='bad sort')


def test_files_respect_folder_deleted_and_blocked(lib, tmp_path):
    settings, db = lib
    folder = tmp_path / 'keep'
    folder.mkdir()
    ids = []
    for n in range(4):
        path = (folder if n < 3 else tmp_path) / f'{n}.mp4'
        path.write_bytes(str(n).encode())
        ids.append(register_file(db, path)[1])
    db.x('UPDATE assets SET deleted_at=1 WHERE id=?', (ids[0],))
    db.x("INSERT INTO rights(asset_id,status,updated_at) VALUES(?,'not_cleared',1)", (ids[1],))
    service = Library(db, settings)
    result = service.list_assets(LOCAL_ADMIN, folder=str(folder), hide_blocked=True, sort='captured_desc')
    assert result['total'] == 1 and result['assets'][0]['filename'] == '2.mp4'
    assert service.list_assets(LOCAL_ADMIN, folder=str(folder), hide_blocked=False)['total'] == 2
