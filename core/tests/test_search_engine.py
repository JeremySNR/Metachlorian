"""Search engine mechanics: paging, facets, strength split, scopes and limits."""
from __future__ import annotations

import posixpath

import pytest

from metachlorian.search import engine as E
from metachlorian.search.engine import SearchEngine, SearchRequest
from metachlorian.service import Library

ALL = {"hide_blocked": False}  # the matrix's ten shots, blocked ones included


@pytest.fixture(scope="module")
def eng(rights_matrix):
    return SearchEngine(rights_matrix["db"], rights_matrix["settings"])


def _uids(res) -> list[str]:
    return [r["uid"] for r in res["results"]]


def test_cursor_round_trip_visits_every_shot_once(eng, rights_matrix):
    first = eng.search(SearchRequest(q="", limit=40, facets=False, **ALL))
    seen, cursor, pages = [], None, 0
    while True:
        res = eng.search(SearchRequest(q="", limit=3, cursor=cursor, facets=False, **ALL))
        assert res["total"] == first["total"] == 10
        seen += _uids(res)
        pages += 1
        cursor = res["next_cursor"]
        if not cursor:
            break
    assert pages == 4 and seen == _uids(first)


def test_a_cursor_from_another_query_is_ignored(eng):
    a = eng.search(SearchRequest(q="", limit=3, facets=False, **ALL))
    b_first = eng.search(SearchRequest(q="", limit=3, facets=False, filters={"min_duration": 1.0}, **ALL))
    b_with_a_cursor = eng.search(SearchRequest(q="", limit=3, facets=False, filters={"min_duration": 1.0}, cursor=a["next_cursor"], **ALL))
    assert _uids(b_with_a_cursor) == _uids(b_first)
    assert _uids(eng.search(SearchRequest(q="", limit=3, cursor="not base64 at all!", facets=False, **ALL))) == _uids(a)


def test_facets_count_only_the_filtered_pool(eng, rights_matrix):
    whole = eng.search(SearchRequest(q="", limit=1, **ALL))
    one = eng.search(SearchRequest(q="", limit=1, asset_uids=[rights_matrix["assets"]["unknown"]], **ALL))
    assert whole["total"] == 10 and one["total"] == 2
    for name in ("orientation", "resolution", "edit_type", "shot_role"):
        assert sum(f["count"] for f in whole["facets"][name]) == 10
        assert sum(f["count"] for f in one["facets"][name]) == 2
    hidden = eng.search(SearchRequest(q="", limit=1))  # blocked footage hidden: facets follow the visible pool
    assert sum(f["count"] for f in hidden["facets"]["orientation"]) == hidden["total"] == 5
    assert eng.search(SearchRequest(q="", limit=1, facets=False, **ALL))["facets"] == {}


@pytest.mark.parametrize("strictness", tuple(E.STRENGTH_THRESHOLDS))
def test_strictness_splits_strong_from_weak(eng, monkeypatch, strictness):
    """Strong matches (strength >= the threshold for the chosen strictness) come first, then the rest in rank order."""
    base = eng.search(SearchRequest(q="", limit=40, facets=False, **ALL))
    order = [r["uid"] for r in base["results"]]
    ids = {u: eng.db.q1("SELECT id FROM shots WHERE uid=?", (u,))["id"] for u in order}
    levels = [0.1, 0.3, 0.5, 0.7, 0.9]
    fake = {ids[u]: levels[i % len(levels)] for i, u in enumerate(order)}
    monkeypatch.setattr(SearchEngine, "_strengths", lambda self, pool, *a, **k: {s: fake[s] for s in pool})
    res = eng.search(SearchRequest(q="", limit=40, facets=False, strictness=strictness, **ALL))
    t = E.STRENGTH_THRESHOLDS[strictness]
    strong = [u for u in order if fake[ids[u]] >= t]
    assert _uids(res) == strong + [u for u in order if u not in strong]
    assert res["strong_count"] == len(strong) and res["strictness"] == strictness
    assert all(r["strong"] == (r["strength"] >= t) for r in res["results"])


def test_unknown_strictness_falls_back_to_balanced(eng, monkeypatch):
    monkeypatch.setattr(SearchEngine, "_strengths", lambda self, pool, *a, **k: {s: 0.5 for s in pool})
    res = eng.search(SearchRequest(q="", limit=40, facets=False, strictness="whatever", **ALL))
    assert res["strong_count"] == 10  # 0.5 >= balanced (0.4)


def test_folder_and_collection_scopes_compose_with_filters(rights_matrix, principals):
    lib = Library(rights_matrix["db"], rights_matrix["settings"])
    admin = principals["admin"]
    folder = posixpath.basename(str(rights_matrix["settings"].data_dir.parent / "footage"))
    res = lib.search(admin, {"q": "", "limit": 40, "facets": False, "filters": {"folder": folder}, **ALL})
    assert res["total"] == 10 and res["query"]["filters"]["folder"] == [folder]
    assert lib.search(admin, {"q": "", "facets": False, "filters": {"folder": "no such folder"}, **ALL})["total"] == 0
    c = lib.create_collection(admin, "scope test " + folder)
    picks = rights_matrix["shots"]["unknown"] + rights_matrix["shots"]["editorial_only"][:1]
    lib.add_to_collection(admin, c["uid"], picks)
    try:
        res = lib.search(admin, {"q": "", "limit": 40, "facets": False, "filters": {"collection": c["uid"], "folder": folder}})
        assert set(_uids(res)) == set(picks)
        # A filter narrows the scope further; an asset filter outside it leaves nothing.
        res = lib.search(admin, {"q": "", "facets": False, "filters": {"collection": c["name"]}, "asset_uids": [rights_matrix["assets"]["unknown"]]})
        assert set(_uids(res)) == set(rights_matrix["shots"]["unknown"])
        res = lib.search(admin, {"q": "", "facets": False, "filters": {"collection": c["uid"]}, "asset_uids": [rights_matrix["assets"]["expired"]], **ALL})
        assert res["total"] == 0
        # The scope can be written in the query text too.
        res = lib.search(admin, {"q": f'collection:"{c["name"]}"', "limit": 40, "facets": False})
        assert set(_uids(res)) == set(picks)
    finally:
        lib.delete_collection(admin, c["uid"])


@pytest.mark.parametrize("asked,got", ((1, 1), (3, 3), (500, 10), (-5, 1)))
def test_limit_is_bounded(eng, asked, got):
    res = eng.search(SearchRequest(q="", limit=asked, facets=False, **ALL))
    assert len(res["results"]) == got
    assert res["query"]["limit"] == max(1, min(200, asked))


def test_empty_query_with_a_scope_orders_by_quality(processed):
    s, db, a = processed
    shots = db.q("SELECT shot_id FROM shot_index WHERE asset_id=? ORDER BY start_s", (a["id"],))
    for q, r in zip((0.2, 0.9, 0.5), shots):
        db.x("UPDATE shot_index SET quality=? WHERE shot_id=?", (q, r["shot_id"]))
    eng = SearchEngine(db, s)
    folder = posixpath.basename(posixpath.dirname(a["path"].replace("\\", "/")))
    res = eng.search(SearchRequest(q="", filters={"folder": folder}, facets=False))
    quality = [db.q1("SELECT quality FROM shot_index si JOIN shots s ON s.id=si.shot_id WHERE s.uid=?", (u,))["quality"] for u in _uids(res)]
    assert quality == sorted(quality, reverse=True) == [0.9, 0.5, 0.2]
