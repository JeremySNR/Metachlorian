from metachlorian.auth import LOCAL_ADMIN
from metachlorian.service import Library


def test_processing_counts_entire_library_beyond_display_limit(lib):
    s, db = lib
    statuses = ['ready'] * 205 + ['processing'] * 40 + ['updating'] * 20 + ['missing'] * 2
    with db.tx() as c:
        c.executemany(
            "INSERT INTO assets(uid,path,filename,size,mtime,quick_hash,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            [(f'a{i}', f'/a{i}.mp4', f'a{i}.mp4', 1, 0, f'q{i}', status, 0, 0)
             for i, status in enumerate(statuses)])
    db.x("UPDATE assets SET deleted_at=1 WHERE uid='a0'")
    result = Library(db, s).processing(LOCAL_ADMIN)
    assert len(result['assets']) == 200
    assert result['asset_counts'] == {'ready': 204, 'processing': 40, 'updating': 20, 'missing': 2}
    assert sum(result['asset_counts'].values()) == 266


def test_retry_all_does_not_rerun_superseded_failure(lib):
    from metachlorian.jobs import queue

    s, db = lib
    db.x("INSERT INTO assets(uid,path,filename,size,mtime,quick_hash,status,created_at,updated_at) "
         "VALUES('a','/a.mp4','a.mp4',1,0,'q','missing',0,0)")
    aid = db.q1('SELECT id FROM assets')[0]
    for analyser, key in [('keyframes', 'old'), ('keyframes', 'new'), ('speech', 'current')]:
        queue.enqueue(db, aid, analyser, key, 1)
    db.x("UPDATE jobs SET status='failed',error='failure'")
    db.x("UPDATE jobs SET status='done' WHERE input_key='new'")
    for analyser, key, status in [('keyframes', 'new', 'done'), ('speech', 'current', 'failed')]:
        db.x("INSERT INTO analysis_runs(asset_id,analyser,version,input_key,status,output) VALUES(?,?,?,?,?,?)",
             (aid, analyser, '1', key, status, '{}'))
    Library(db, s).retry_failed(LOCAL_ADMIN)
    assert dict(db.q1("SELECT status,error FROM jobs WHERE input_key='current'")) == {'status': 'queued', 'error': None}
    assert db.q1("SELECT status FROM jobs WHERE input_key='old'")[0] == 'failed'
    assert queue.stats(db)['by_status'].get('failed', 0) == 0
