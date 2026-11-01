"""Search indexing failures are durable and recover without repeating analysis."""
from metachlorian import indexer, pipeline
from metachlorian.analysers import registry
from metachlorian.analysers.base import AnalysisContext
from metachlorian.db import dumps, loads


def _marker(db, aid):
    row = db.q1('SELECT value FROM meta WHERE key=?', (f'index:asset:{aid}',))
    return loads(row['value']) if row else None


def test_index_failure_survives_planning_then_recovers_without_analysis(processed, monkeypatch):
    settings, db, asset = processed
    aid = asset['id']
    original = indexer.index_asset
    clock = [1000.0]
    monkeypatch.setattr(pipeline, 'now', lambda: clock[0])
    calls = []

    def fail(*args):
        calls.append(True)
        raise ValueError('bad search field')

    before = [tuple(r) for r in db.q('SELECT * FROM analysis_runs WHERE asset_id=? ORDER BY id', (aid,))]
    db.x('INSERT INTO meta(key,value) VALUES(?,?)', (f'index:asset:{aid}', dumps({'status': 'pending'})))
    monkeypatch.setattr(indexer, 'index_asset', fail)
    assert pipeline.plan_asset(db, settings, aid) == []
    state = _marker(db, aid)
    assert state['status'] == 'failed' and state['attempts'] == 1
    assert 'bad search field' in state['error'] and state['next_retry_at'] == 1030
    assert db.q1('SELECT status FROM assets WHERE id=?', (aid,))[0] == 'error'
    # Frequent planning during ingestion does not hammer the failing indexer.
    for _ in range(4):
        pipeline.plan_asset(db, settings, aid)
    assert len(calls) == 1
    clock[0] = 1030
    pipeline.plan_asset(db, settings, aid)
    assert len(calls) == 2 and _marker(db, aid)['next_retry_at'] == 1090
    monkeypatch.setattr(indexer, 'index_asset', original)
    clock[0] = 1090
    assert pipeline.plan_asset(db, settings, aid) == []
    assert _marker(db, aid) is None
    assert db.q1('SELECT status FROM assets WHERE id=?', (aid,))[0] == 'ready'
    assert [tuple(r) for r in db.q('SELECT * FROM analysis_runs WHERE asset_id=? ORDER BY id', (aid,))] == before


def test_existing_unindexed_shots_are_repaired_on_plan(processed):
    settings, db, asset = processed
    aid = asset['id']
    before = [r[0] for r in db.q('SELECT shot_id FROM shot_index WHERE asset_id=? ORDER BY shot_id', (aid,))]
    db.x('DELETE FROM shot_index WHERE shot_id=?', (before[0],))
    assert _marker(db, aid) is None
    assert pipeline.plan_asset(db, settings, aid) == []
    assert [r[0] for r in db.q('SELECT shot_id FROM shot_index WHERE asset_id=? ORDER BY shot_id', (aid,))] == before
    assert _marker(db, aid) is None


def test_commit_records_pending_index_and_does_not_lose_newer_refresh(processed, monkeypatch):
    settings, db, asset = processed
    aid = asset['id']
    job = dict(db.q1("SELECT * FROM jobs WHERE asset_id=? AND analyser='motion' ORDER BY id DESC LIMIT 1", (aid,)))
    db.x("UPDATE jobs SET status='running' WHERE id=?", (job['id'],))
    analyser = registry.get('motion')
    ctx = AnalysisContext(db, settings, asset, analyser)
    pipeline.commit(db, job, analyser, ctx, 'done', {}, None, pipeline.now())
    assert _marker(db, aid)['status'] == 'pending'
    original = indexer.index_asset

    def concurrent_commit(*args):
        count = original(*args)
        db.x('UPDATE meta SET value=? WHERE key=?',
             (dumps({'status': 'pending', 'updated_at': 99999999999}), f'index:asset:{aid}'))
        return count

    monkeypatch.setattr(indexer, 'index_asset', concurrent_commit)
    pipeline._refresh_index(db, settings, aid)
    assert _marker(db, aid)['updated_at'] == 99999999999
    monkeypatch.setattr(indexer, 'index_asset', original)
    pipeline.plan_asset(db, settings, aid)
    assert _marker(db, aid) is None


def test_log_search_provenance_distinguishes_metadata_from_estimates(processed, monkeypatch):
    settings, db, asset = processed
    docs = indexer.build_shot_docs(db, asset['id'])
    monkeypatch.setattr(indexer, 'build_shot_docs', lambda *args: docs)
    for source, expected in [('metadata', 'technical'), ('metadata_hint', 'metadata_hint'), ('image_estimate', 'quality')]:
        for doc in docs:
            doc['technical'].update(log_profile=True, log_confidence=0.9, log_profile_source=source)
        indexer.index_asset(db, settings, asset['id'])
        sources = {r[0] for r in db.q("SELECT source FROM shot_terms WHERE vocab='look' AND term='log'")}
        assert sources == {expected}
