"""Camera dates stay trustworthy across legacy imports, browsing and search."""
import sqlite3

import pytest

from metachlorian.capture_dates import capture_calendar_sql, capture_day_sql, capture_iso
from metachlorian.db import dumps, loads
from metachlorian.folders import list_folders
from metachlorian.indexer import index_asset
from metachlorian.ingest.scan import add_source, register_file
from metachlorian.search.engine import SearchEngine, SearchRequest


@pytest.mark.parametrize('raw,day', [
    ('2024:02:29 23:59:59-05:00', '2024-02-29'),
    ('2024-02-29T00:00:01+14:00', '2024-02-29'),
    (' 2024:02:29 12:34:56 ', '2024-02-29'),
    ('2025-10-01', '2025-10-01'),
    ('0000:00:00 00:00:00', None),
    ('2025:02:29 12:00:00', None),
    ('2024:04:31 12:00:00', None),
    ('0000-01-01', None),
    ('not a date', None),
    (None, None),
])
def test_camera_date_formats_and_invalid_metadata(raw, day):
    with sqlite3.connect(':memory:') as db:
        row = db.execute(f'SELECT {capture_calendar_sql("value")}, {capture_day_sql("value")} '
                         'FROM (SELECT ? value)', (raw,)).fetchone()
    iso = capture_iso(raw)
    assert (iso[:10] if iso else None) == day
    assert row[0] == day
    assert (row[1] is not None) == (day is not None)


def _add_asset(db, path, date, idx):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(idx).encode())
    _, aid = register_file(db, path)
    db.x('UPDATE assets SET tech=? WHERE id=?', (dumps({'capture_date': date}), aid))
    return aid


def test_folder_ranges_ignore_missing_invalid_dates_and_file_mtime(lib, tmp_path):
    _, db = lib
    root = tmp_path / 'footage'
    add_source(db, str(root))
    _add_asset(db, root / 'known' / 'late.mp4', '2024:04:05 23:30:00-05:00', 1)
    _add_asset(db, root / 'known' / 'early.mp4', '2024-04-06T00:15:00+14:00', 2)
    _add_asset(db, root / 'unknown' / 'missing.mp4', None, 3)
    _add_asset(db, root / 'unknown' / 'invalid.mp4', '0000:00:00 00:00:00', 4)
    # An identical file in a second folder contributes one file to each folder,
    # but only once to their shared parent's date coverage.
    duplicate = root / 'unknown' / 'copy.mp4'
    duplicate.write_bytes(b'1')
    register_file(db, duplicate)
    folders = {f['name']: f for f in list_folders(db)['folders']}
    parent = folders['footage']
    assert parent['files'] == 4
    assert (parent['captured_from'], parent['captured_to']) == ('2024-04-05', '2024-04-06')
    assert (parent['capture_dates_known'], parent['capture_dates_unknown']) == (2, 2)
    assert folders['unknown']['captured_from'] == '2024-04-05'
    assert folders['unknown']['capture_dates_unknown'] == 2
    # A truly undated folder must not claim its files were shot on their modification day.
    _add_asset(db, root / 'undated' / 'missing.mp4', None, 5)
    undated = next(f for f in list_folders(db)['folders'] if f['name'] == 'undated')
    assert undated['captured_from'] is None and undated['captured_to'] is None


def test_date_filters_include_entire_recorded_day_and_legacy_rows(lib, tmp_path):
    settings, db = lib
    dates = ['2024:04:05 23:30:00-05:00', '2024-04-05T00:15:00+14:00',
             '2024:04:04 23:59:59', '2024-04-06T00:00:00Z', None, '0000:00:00 00:00:00']
    for i, date in enumerate(dates):
        aid = _add_asset(db, tmp_path / f'{i}.mp4', date, i)
        db.x("INSERT INTO shots(uid,asset_id,idx,start_s,end_s,start_frame,end_frame,segmenter) VALUES(?,?,0,0,1,0,25,'test')",
             (f'shot-{i}', aid))
        index_asset(db, settings, aid)
        # New indexes normalize their sortable column, preserving source evidence.
        indexed = db.q1('SELECT capture_date,doc FROM shot_index WHERE asset_id=?', (aid,))
        assert indexed['capture_date'] == capture_iso(date)
        assert loads(indexed['doc'])['technical'].get('capture_date') == date
        if i % 2 == 0:
            db.x('UPDATE shot_index SET capture_date=? WHERE asset_id=?', (date, aid))
    engine = SearchEngine(db, settings)

    def search(**filters):
        return {r['uid'] for r in engine.search(SearchRequest(filters=filters, hide_blocked=False, facets=False))['results']}

    assert search(captured_after='2024-04-05', captured_before='2024-04-05') == {'shot-0', 'shot-1'}
    assert search(captured_before='2024-04-05') == {'shot-0', 'shot-1', 'shot-2'}
    assert search(captured_after='2024-04-05') == {'shot-0', 'shot-1', 'shot-3'}
    # Explicit timestamps retain instant semantics, including timezone offsets.
    assert search(captured_after='2024-04-06T04:00:00Z') == {'shot-0'}
    with pytest.raises(ValueError, match='captured_before must be a valid'):
        search(captured_before='2024-02-30')
