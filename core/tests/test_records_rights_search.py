import json

import pytest

from metachlorian import rights as R
from metachlorian.indexer import index_asset
from metachlorian.ingest.scan import add_source, scan_source
from metachlorian.records import build_shot_doc, record_correction
from metachlorian.search.engine import SearchEngine, SearchRequest
from metachlorian.search.parse import parse

from .test_ingest_pipeline import run_all


@pytest.fixture()
def processed(lib, footage):
    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    run_all(s, db)
    a = db.q1("SELECT * FROM assets")
    return s, db, a


def test_correction_wins_and_survives_reprocessing(processed):
    s, db, a = processed
    shot = db.q1("SELECT * FROM shots WHERE asset_id=? AND idx=1", (a["id"],))
    record_correction(db, "shot", a["uid"], "camera.shot_size", "set", "close_up", "alice", None, shot["uid"], "it is a close-up")
    record_correction(db, "shot", a["uid"], "camera.movement", "add", "handheld", "alice", None, shot["uid"])
    doc = build_shot_doc(db, shot["id"])
    assert doc["fields"]["camera.shot_size"]["value"]["term"] == "close_up"
    assert doc["fields"]["camera.shot_size"]["source"] == "human"
    assert any(m["term"] == "handheld" for m in doc["fields"]["camera.movement"]["value"])
    # Re-process everything from scratch: machine output is replaced, corrections are not.
    db.x("DELETE FROM analysis_runs")
    db.x("DELETE FROM jobs")
    run_all(s, db)
    shot2 = db.q1("SELECT * FROM shots WHERE asset_id=? AND idx=1", (a["id"],))
    doc = build_shot_doc(db, shot2["id"])
    assert doc["fields"]["camera.shot_size"]["value"]["term"] == "close_up"
    assert doc["fields"]["camera.shot_size"]["corrected"] is True
    # The search index reflects the correction.
    index_asset(db, s, a["id"])
    t = db.q1("SELECT source FROM shot_terms WHERE shot_id=? AND vocab='shot_size' AND term='close_up'", (shot2["id"],))
    assert t and t["source"] == "human"


def test_correction_reattaches_after_resegmentation(processed):
    s, db, a = processed
    shot = db.q1("SELECT * FROM shots WHERE asset_id=? AND idx=2", (a["id"],))
    record_correction(db, "shot", a["uid"], "shot.role", "set", ["insert"], "bob", None, shot["uid"])
    # Simulate a new segmenter that moved the boundary by a few frames (new shot uid).
    db.x("UPDATE shots SET uid=?, start_frame=start_frame+3 WHERE id=?", (shot["uid"] + "x", shot["id"]))
    doc = build_shot_doc(db, shot["id"])
    assert doc["fields"]["shot.role"]["value"][0]["term"] == "insert"


def test_invalid_corrections_rejected(processed):
    s, db, a = processed
    shot = db.q1("SELECT * FROM shots WHERE asset_id=? LIMIT 1", (a["id"],))
    with pytest.raises(ValueError):
        record_correction(db, "shot", a["uid"], "camera.shot_size", "set", "very_wide_indeed", "x", None, shot["uid"])
    with pytest.raises(ValueError):
        record_correction(db, "shot", a["uid"], "technical.fps", "set", 25, "x", None, shot["uid"])


def test_rights_checks():
    r = {**R.empty(), "status": "cleared", "permitted_uses": ["marketing", "editorial"], "channels": ["social"], "territories": ["GB", "PT"],
         "expires": "2099-01-01", "model_release": "unlimited"}
    assert R.check(r, "marketing", "paid_social", "PT")["verdict"] == "allowed"  # social covers paid_social
    assert R.check(r, "advertising", "paid_social", "PT")["verdict"] == "blocked"
    assert R.check(r, "marketing", "broadcast", "PT")["verdict"] == "blocked"
    assert R.check(r, "marketing", "paid_social", "US")["verdict"] == "blocked"
    assert R.check({**r, "expires": "2000-01-01"}, "marketing")["verdict"] == "blocked"
    assert R.check({**r, "model_release": "unknown"}, "marketing", people_visible=True)["verdict"] == "restricted"
    assert R.check(R.empty(), "marketing")["verdict"] == "unknown"
    assert R.check({**r, "status": "not_cleared"})["verdict"] == "blocked"
    assert R.summary_status({**r, "expires": "2000-01-01"}) == "expired"


def test_rights_validation(processed):
    s, db, a = processed
    with pytest.raises(ValueError):
        R.set_rights(db, a["id"], {"channels": ["telepathy"]}, "x")
    with pytest.raises(ValueError):
        R.set_rights(db, a["id"], {"territories": ["Portugal"]}, "x")
    out = R.set_rights(db, a["id"], {"status": "cleared", "channels": ["web"], "territories": ["pt"]}, "x")
    assert out["territories"] == ["PT"]


def test_parser_spec_queries():
    p = parse("Find slow, wide drone shots of a coastline at golden hour, no people, at least 8 seconds, 4K.")
    assert p.filters == {"min_duration": 8.0, "min_height": 2160, "max_people": 0}
    assert p.prefer["camera_movement"] == ["aerial"] and "coast" in p.prefer["setting"] and p.prefer["time_of_day"] == ["golden_hour"]
    assert "long_shot" in p.prefer["shot_size"] and p.prefer["pace"] == ["slow"]
    p = parse("What do we have from Lisbon that we are actually cleared to use on paid social?")
    assert p.rights == {"channel": "paid_social"} and p.place == ["Lisbon"]
    p = parse("Give me three B-roll cutaways that would work under this interview line about family holidays.")
    assert p.limit == 3 and p.semantic == "family holidays" and "interview" not in p.prefer.get("shot_role", [])
    p = parse("handheld street food close-ups, busy, night")
    assert p.prefer["camera_movement"] == ["handheld"] and p.prefer["time_of_day"] == ["night"] and p.prefer["shot_size"] == ["close_up"]


def test_search_filters_rights_and_explanations(processed):
    s, db, a = processed
    index_asset(db, s, a["id"])
    eng = SearchEngine(db, s)
    r = eng.search(SearchRequest(q="", filters={"min_duration": 1.5}))
    assert r["total"] == 3
    r = eng.search(SearchRequest(q="", filters={"min_duration": 10}))
    assert r["total"] == 0
    r = eng.search(SearchRequest(q="", filters={"min_height": 2160}))
    assert r["total"] == 0  # 320x180 test footage is not 4K
    # Rights: nothing recorded -> nothing returned for an intended use.
    r = eng.search(SearchRequest(q="", intended_use={"use": "marketing", "channel": "paid_social"}))
    assert r["total"] == 0 and r["excluded_by_rights"] == 3
    R.set_rights(db, a["id"], {"status": "cleared", "permitted_uses": ["marketing"], "channels": ["social"]}, "x")
    r = eng.search(SearchRequest(q="", intended_use={"use": "marketing", "channel": "paid_social"}))
    assert r["total"] == 3 and all(x["rights"]["verdict"] == "allowed" for x in r["results"])
    # Explanations name the filters that matched.
    r = eng.search(SearchRequest(q="", filters={"min_duration": 1.5}, limit=1))
    assert any(w["signal"] == "filter" for w in r["results"][0]["why"])
    assert json.dumps(r)  # JSON serialisable


def test_fusion_merge_counts_each_source_once():
    from metachlorian.analysers.fusion import merge_multi

    votes = [([{"term": "open_water", "confidence": 0.8}], 0.75, "vlm")] * 3
    one = merge_multi(votes[:1])[0]
    many = merge_multi(votes)[0]
    assert many["confidence"] == one["confidence"] and many["sources"] == ["vlm"]
    both = merge_multi(votes + [([{"term": "open_water", "confidence": 0.5}], 0.55, "visual_tags")])[0]
    assert both["confidence"] > one["confidence"] and both["sources"] == ["visual_tags", "vlm"]
    # Low-confidence evidence is kept when the caller asks for it.
    assert merge_multi([([{"term": "office", "confidence": 0.3}], 0.55, "visual_tags")], keep=0.12)


def test_vector_index_incremental_and_persistent(tmp_path):
    """Deletes are applied incrementally (no rebuild), ids are never reused, and the index
    reloads from disk including deletions made while it was not running."""
    import time as _t

    import numpy as np

    from metachlorian.db import Database
    from metachlorian.search.vectors import VectorIndex

    db = Database(tmp_path / "v.sqlite")
    db.migrate()
    db.x("PRAGMA foreign_keys=OFF")  # vectors only; no shot rows needed for the index
    rng = np.random.default_rng(0)

    def add(n, shot):
        with db.tx() as c:
            c.executemany("INSERT INTO vectors(shot_id, asset_id, space, dim, vec, created_at) VALUES(?,?,?,?,?,?)",
                          [(shot, 1, "t", 8, rng.standard_normal(8).astype(np.float16).tobytes(), _t.time()) for _ in range(n)])

    add(30_000, 1)
    add(10, 2)
    idx = VectorIndex(db, "t", tmp_path / "idx")
    idx.sync()
    assert len(idx.shot_of) == 30_010 and (tmp_path / "idx" / "t.usearch").exists()
    top = max(idx.shot_of)
    db.x("DELETE FROM vectors WHERE shot_id=2")
    add(5, 2)
    index_obj = idx.index
    idx.sync()
    assert idx.index is index_obj, "deletes must not trigger a rebuild"
    assert len(idx.vids_of[2]) == 5 and min(idx.vids_of[2]) > top, "vector ids must never be reused"
    q = np.frombuffer(db.q1("SELECT vec FROM vectors WHERE shot_id=2 ORDER BY id LIMIT 1")["vec"], dtype=np.float16).astype(np.float32)
    assert idx.search(q, 1, candidates={2})[0][0] == 2
    idx.save()
    # Deleted while no process held the index: the reload must drop them.
    db.x("DELETE FROM vectors WHERE id IN (SELECT id FROM vectors WHERE shot_id=1 ORDER BY id LIMIT 100)")
    again = VectorIndex(db, "t", tmp_path / "idx")
    again.sync()
    assert len(again.shot_of) == 30_010 - 10 + 5 - 100
    assert again.garbage >= 100
    hits = again.search(q, 5)
    assert hits and all(s in (1, 2) for s, _ in hits)


def test_endpoint_locality_is_decided_by_host():
    from metachlorian.config import ModelEndpoint, Settings, classify_endpoint

    assert classify_endpoint("http://127.0.0.1:8080/v1")[0]
    assert classify_endpoint("http://192.168.1.20:11434/v1")[0]
    assert classify_endpoint("http://gpu-box.local:8000/v1")[0]
    assert not classify_endpoint("https://api.openai.com/v1")[0]
    assert not classify_endpoint("https://8.8.8.8/v1")[0]
    s = Settings()
    s.vlm = ModelEndpoint(base_url="https://api.openai.com/v1", model="x", local=True)  # self-declared local
    assert not s.vlm.is_local and not s.endpoint_allowed(s.vlm)
    assert s.egress_summary()["adapters"][0]["adapter"] == "vlm"


def test_rule_caption_follows_corrections_and_skips_weak_guesses():
    from metachlorian.records import _refresh_template_caption

    fields = {
        "camera.shot_size": {"value": {"term": "extreme_close_up", "confidence": 0.41}, "source": "fusion"},
        "content.time_of_day": {"value": {"term": "night", "confidence": 0.7}, "source": "fusion"},
        "people.count": {"value": {"value": 2, "confidence": 0.75}, "source": "fusion"},
        "content.caption": {"value": {"value": "old", "confidence": 0.35, "sources": ["fusion_rules"]}, "source": "fusion"},
    }
    _refresh_template_caption(fields)
    cap = fields["content.caption"]["value"]["value"]
    assert "close-up" not in cap.lower() and "Night" in cap and "2 people" in cap
    fields["content.time_of_day"] = {"value": {"term": "morning", "confidence": 1.0, "sources": ["human"]}, "source": "human", "corrected": True}
    _refresh_template_caption(fields)
    cap = fields["content.caption"]["value"]["value"]
    assert "night" not in cap.lower() and "morning" in cap.lower()
