import pytest

from metachlorian.auth import LOCAL_ADMIN, Principal, Forbidden
from metachlorian.db import dumps
from metachlorian.ingest.scan import register_file, add_source
from metachlorian.service import Library


def test_readiness_separates_search_coverage_from_analysis(lib, tmp_path):
    settings, db = lib
    ids = []
    for n in range(3):
        path = tmp_path / f'{n}.mp4'
        path.write_bytes(str(n).encode())
        _, aid = register_file(db, path)
        ids.append(aid)
        db.x("INSERT INTO shots(uid,asset_id,idx,start_s,end_s,start_frame,end_frame,segmenter) VALUES(?,?,0,0,2,0,50,'test')", (f'shot-{aid}', aid))
    # A ready label does not make an unindexed file searchable.
    db.x("UPDATE assets SET status='ready',tech=?", (dumps({'capture_date': '2026:10:25 17:58:44+00:00'}),))
    sid = db.q1('SELECT id FROM shots WHERE asset_id=?', (ids[0],))['id']
    db.x("INSERT INTO shot_index(shot_id,asset_id,doc,updated_at) VALUES(?,?,'{}',1)", (sid, ids[0]))
    db.x("INSERT INTO analysis_runs(asset_id,analyser,version,input_key,status,error) VALUES(?,'caption','1','x','failed','Provider stopped')", (ids[0],))
    db.x("INSERT INTO analysis_runs(asset_id,analyser,version,input_key,status) VALUES(?,'speech','1','x','unavailable')", (ids[1],))
    db.set_meta(f'index:asset:{ids[1]}', dumps({'status': 'failed', 'error': 'database full', 'next_retry_at': 123}))
    # Deleted footage must not inflate diagnostics or expose obsolete failures.
    db.x('UPDATE assets SET deleted_at=1 WHERE id=?', (ids[2],))
    db.x("INSERT INTO analysis_runs(asset_id,analyser,version,input_key,status) VALUES(?,'caption','1','x','failed')", (ids[2],))
    service = Library(db, settings)
    d = service.library_readiness(LOCAL_ADMIN)
    assert d['files']['total'] == 2 and d['files']['searchable'] == 1 and d['files']['unindexed'] == 1
    assert d['shots'] == {'active': 2, 'indexed': 1, 'missing_from_index': 1}
    assert d['files']['capture_date_known'] == 2 and d['files']['index_failed'] == 1
    assert d['failed_analysis_files'] == 1 and d['limited_analysis_files'] == 1
    assert d['analysis']['caption'] == {'failed': 1}
    assert d['state'] == 'attention' and len(d['failures']) == 1
    assert d['index_issues'][0]['next_retry_at'] == 123
    with pytest.raises(Forbidden):
        service.library_readiness(Principal(None, 'no-access', 'agent', set(), 'mcp'))


def test_empty_library_can_still_be_scanning(lib, tmp_path):
    settings, db = lib
    service = Library(db, settings)
    assert service.library_readiness(LOCAL_ADMIN)['state'] == 'empty'
    source = add_source(db, str(tmp_path))
    for state in ('queued', 'discovering', 'registering'):
        db.set_meta(f'scan:{source}', dumps({'state': state}))
        assert service.library_readiness(LOCAL_ADMIN)['state'] == 'processing'
    db.set_meta(f'scan:{source}', dumps({'state': 'completed_with_errors'}))
    assert service.library_readiness(LOCAL_ADMIN)['state'] == 'attention'
