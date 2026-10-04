import shutil

from metachlorian import pipeline
from metachlorian.analysers import registry
from metachlorian.indexer import index_asset
from metachlorian.ingest.scan import add_source, scan_source
from metachlorian.jobs import queue

from .conftest import run_all


def test_ingest_dedupe_and_unchanged(lib, footage):
    s, db = lib
    sid = add_source(db, str(footage))
    r = scan_source(db, sid)
    assert r.added == 1
    # Unchanged on rescan.
    r = scan_source(db, sid)
    assert r.unchanged == 1 and r.added == 0
    # The same bytes under another name are a duplicate, not a new asset.
    shutil.copy(footage / "clip_a.mp4", footage / "copy_of_a.mp4")
    r = scan_source(db, sid)
    assert r.duplicates == 1
    assert db.q1("SELECT COUNT(*) n FROM assets")["n"] == 1
    assert db.q1("SELECT COUNT(*) n FROM asset_paths")["n"] == 2
    # Removing one copy keeps the asset; removing both marks it missing.
    (footage / "clip_a.mp4").unlink()
    scan_source(db, sid)
    assert db.q1("SELECT status FROM assets")["status"] != "missing"
    (footage / "copy_of_a.mp4").unlink()
    r = scan_source(db, sid)
    assert r.missing == 1


def test_pipeline_deterministic_and_idempotent(lib, footage):
    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    n = run_all(s, db)
    assert n >= 10
    a = db.q1("SELECT * FROM assets")
    assert a["status"] == "ready", [dict(r) for r in db.q("SELECT analyser, status, error FROM analysis_runs")]
    # Three synthetic sources joined by hard cuts -> three shots.
    shots = db.q("SELECT start_s, end_s, transition_in FROM shots WHERE asset_id=? ORDER BY idx", (a["id"],))
    assert len(shots) == 3
    assert abs(shots[1]["start_s"] - 2.0) < 0.1 and abs(shots[2]["start_s"] - 4.0) < 0.1
    # Measured signals carry source, confidence and model version.
    sig = db.q1("SELECT * FROM signals WHERE name='camera.movement' LIMIT 1")
    assert sig["source"] == "motion" and sig["model_version"] and sig["confidence"] is not None
    # Unavailable analysers (no models installed in tests) are recorded, not faked.
    runs = {r["analyser"]: r["status"] for r in db.q("SELECT analyser, status FROM analysis_runs")}
    assert runs["technical"] == "done" and runs["shots"] == "done" and runs["fusion"] == "done"
    assert runs["caption"] == "unavailable"
    # Nothing to do on a second plan: unchanged files are never re-processed.
    assert pipeline.plan_asset(db, s, a["id"]) == []
    # Rollup classified the file and summarised structure.
    summary = db.q1("SELECT summary FROM assets")["summary"]
    assert '"edit_type"' in summary and '"shot_count":3' in summary


def test_upgrading_one_analyser_reruns_only_it_and_dependants(lib, footage, monkeypatch):
    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    run_all(s, db)
    a = db.q1("SELECT id FROM assets")
    quality = registry.get("quality")
    monkeypatch.setattr(type(quality), "version", "9.9.9")
    enq = pipeline.plan_asset(db, s, a["id"])
    # Quality and the analysers downstream of it re-run; segmentation, motion, proxy do not.
    assert "quality" in enq
    assert not {"technical", "proxy", "shots", "keyframes", "motion"} & set(enq)
    run_all(s, db)
    assert db.q1("SELECT version FROM analysis_runs WHERE analyser='quality'")["version"] == "9.9.9"


def test_job_lease_recovery(lib, footage):
    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    pipeline.plan_all(db, s)
    job = queue.claim(db, "crashed-worker")
    assert job
    # Simulate a crash: lease expires, another worker picks the job up.
    db.x("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))
    again = queue.claim(db, "second-worker")
    assert again and again["id"] == job["id"] and again["attempts"] == 2


def test_index_builds_query_rows(lib, footage):
    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    run_all(s, db)
    a = db.q1("SELECT id FROM assets")
    assert index_asset(db, s, a["id"]) == 3
    assert db.q1("SELECT COUNT(*) n FROM shot_index")["n"] == 3
    assert db.q1("SELECT COUNT(*) n FROM shot_fts")["n"] == 3
