"""Face identity: clustering, naming that survives re-analysis, merge, "not this person", search by name, forget."""
import numpy as np
import pytest

from metachlorian import people as PP
from metachlorian.auth import Forbidden, Principal
from metachlorian.indexer import index_asset
from metachlorian.ingest.scan import add_source, scan_source
from metachlorian.search.engine import SearchEngine, SearchRequest
from metachlorian.service import Library

from .test_ingest_pipeline import run_all


@pytest.fixture()
def processed(lib, footage):
    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    run_all(s, db)
    return s, db, db.q1("SELECT * FROM assets")


def _person(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(128).astype(np.float32)
    return v / np.linalg.norm(v)


def _jitter(v: np.ndarray, seed: int, amount: float = 0.35) -> np.ndarray:
    n = np.random.default_rng(seed).standard_normal(128).astype(np.float32)
    w = v + amount * n / np.linalg.norm(n)
    return w / np.linalg.norm(w)


def _faces(shots, specs):
    """specs: (shot index, person vector, seed, t) -> face dicts like the analyser produces."""
    out = []
    for k, (si, vec, seed, t) in enumerate(specs):
        x = 0.1 + 0.45 * (k % 2)  # two people side by side in each shot
        out.append({"shot_id": shots[si]["id"], "t": t, "box": [x, 0.2, x + 0.2, 0.5], "score": 0.95, "size_px": 120,
                    "appearances": 1, "thumb": f"faces/{si:05d}_{k}.jpg", "embedding": _jitter(vec, seed)})
    return out


def test_people_cluster_name_merge_and_survive_reanalysis(processed):
    s, db, a = processed
    shots = [dict(r) for r in db.q("SELECT id, uid, start_s, end_s FROM shots WHERE asset_id=? AND active=1 ORDER BY idx", (a["id"],))]
    assert len(shots) >= 2
    maria, john = _person(1), _person(2)
    specs = [(0, maria, 10, shots[0]["start_s"] + 0.1), (0, john, 11, shots[0]["start_s"] + 0.2),
             (1, maria, 12, shots[1]["start_s"] + 0.1), (1, john, 13, shots[1]["start_s"] + 0.3)]
    with db.tx() as c:
        PP.replace_asset_faces(c, a["id"], _faces(shots, specs))
    lst = PP.list_people(db)["people"]
    assert len(lst) == 2 and all(p["shots"] == 2 for p in lst)
    by_face = {r["t"]: r["identity_id"] for r in db.q("SELECT t, identity_id FROM faces WHERE asset_id=?", (a["id"],))}
    m_id = by_face[specs[0][3]]
    j_id = by_face[specs[1][3]]
    assert m_id != j_id and by_face[specs[2][3]] == m_id and by_face[specs[3][3]] == j_id

    PP.rename(db, m_id, "Maria Silva", "editor")
    index_asset(db, s, a["id"])
    eng = SearchEngine(db, s)
    res = eng.search(SearchRequest(q="maria silva", limit=20, hide_blocked=False))
    found = {r["uid"] for r in res["results"]}
    assert found == {shots[0]["uid"], shots[1]["uid"]} and any("Maria" in n for n in res["notes"])
    assert {p["name"] for r in res["results"] for p in r["identities"]} >= {"Maria Silva"}
    assert res["query"]["people"] == [{"id": m_id, "name": "Maria Silva"}]
    assert res["strong_count"] == len(res["results"])  # a name-only query: every shot with them is a strong match
    with pytest.raises(ValueError, match="merge"):
        PP.rename(db, j_id, "maria silva", "editor")  # names are unique

    # Re-analysis replaces the faces; the human naming re-attaches by time and box.
    with db.tx() as c:
        PP.replace_asset_faces(c, a["id"], _faces(shots, specs))
    again = {r["t"]: (r["identity_id"], r["assigned_by"]) for r in db.q("SELECT t, identity_id, assigned_by FROM faces WHERE asset_id=?", (a["id"],))}
    assert again[specs[0][3]] == (m_id, "named") and again[specs[2][3]] == (m_id, "named")

    # "Not this person" puts a face on a new person and never back on Maria automatically.
    fid = db.q1("SELECT id FROM faces WHERE asset_id=? AND t=?", (a["id"], specs[2][3]))["id"]
    new_id = PP.move_face(db, fid, None)
    assert new_id not in (m_id, j_id)
    assert db.q1("SELECT excluded_identity FROM faces WHERE id=?", (fid,))["excluded_identity"] == m_id

    # Merge John into Maria's new split-off, then forget them.
    PP.merge(db, j_id, new_id)
    assert db.q1("SELECT COUNT(*) n FROM faces WHERE identity_id=?", (new_id,))["n"] == 3
    affected, thumbs = PP.forget(db, new_id)
    assert affected == [a["id"]] and len(thumbs) == 3
    assert db.q1("SELECT COUNT(*) n FROM faces WHERE identity_id=?", (new_id,))["n"] == 0


def test_agents_cannot_name_people(processed):
    s, db, a = processed
    agent = Principal(user_id=None, username="bot", role="agent", scopes={"library:read", "tags:write"})
    with pytest.raises(Forbidden):
        Library(db, s).rename_person(agent, 1, "Someone")
