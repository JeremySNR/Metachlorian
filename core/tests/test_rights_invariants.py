"""Rights invariants: no exit hands out a blocked shot, or a shot an agent is not cleared for, outside the rules.

Every exit is exercised for every kind of caller against a library holding a file in each rights state
(the session `rights_matrix` fixture): search, similar (by shot, image and clip), export_clip in every
mode, build_package, the /media route and the MCP tools. The rules themselves live in rights.gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import anyio
import numpy as np
import pytest
from fastapi.testclient import TestClient

from metachlorian import auth as A
from metachlorian import rights as R
from metachlorian.auth import Forbidden, Principal
from metachlorian.service import Library

from .conftest import RIGHTS_STATES, make_video

STATES = (*RIGHTS_STATES, "override")
BLOCKED_STATES = {"not_cleared", "expired", "override"}
PEOPLE = ("viewer", "editor", "admin", "local")
AGENTS = ("agent", "agent+export", "agent+collections", "agent+tags")
EXPORTERS = ("editor", "admin", "local", "agent+export")
MEDIA_MODES = ("proxy", "file", "otio", "fcpxml", "edl")
# The intended use the matrix is built around: only the cleared file's first shot is allowed for it.
USE = {"use": "marketing", "channel": "paid_social", "territory": "GB"}
VERDICT_FOR_USE = {"cleared": "allowed", "editorial_only": "blocked", "not_cleared": "blocked", "expired": "blocked", "unknown": "unknown",
                   "override": "blocked"}


@pytest.fixture(scope="module")
def m(rights_matrix):
    lib = Library(rights_matrix["db"], rights_matrix["settings"])
    shots = rights_matrix["shots"]
    by_state = {st: shots[st] for st in RIGHTS_STATES}
    by_state["cleared"] = [u for u in shots["cleared"] if u != rights_matrix["override"]]
    by_state["override"] = [rights_matrix["override"]]
    state_of = {u: st for st, uids in by_state.items() for u in uids}
    return {**rights_matrix, "lib": lib, "by_state": by_state, "state_of": state_of, "blocked": {u for u, st in state_of.items() if st in BLOCKED_STATES}}


def _uids(res: dict) -> list[str]:
    return [r["uid"] for r in res["results"]]


def _exports(m) -> set[str]:
    d = m["settings"].export_dir
    return {p.relative_to(d).as_posix() for p in d.rglob("*")} if d.exists() else set()


# ---------------------------------------------------------------------- the gate itself
GATE_RIGHTS = {"cleared": RIGHTS_STATES["cleared"], "not_cleared": {"status": "not_cleared"},
               "expired": RIGHTS_STATES["expired"], "unknown": {}, "restricted": {"status": "restricted", "expires": "2099-01-01"},
               "restricted_expired": {"status": "restricted", "expires": "2001-01-01"}}


@pytest.mark.parametrize("state", GATE_RIGHTS)
@pytest.mark.parametrize("who", ("editor", "agent+export"))
@pytest.mark.parametrize("mode", R.MODES)
def test_gate_table(principals, state, who, mode):
    r = {**R.empty(), **GATE_RIGHTS[state]}
    p = principals[who]
    v = R.gate(r, principal=p, mode=mode, intended=USE)
    blocked = state in ("not_cleared", "expired", "restricted_expired")
    assert v.blocked == blocked
    if mode == "reference":
        assert v.permitted
    elif mode == "list":
        assert v.permitted == (state == "cleared")  # with an intended use, only 'allowed' is listed, for everyone
        assert R.gate(r, principal=p, mode=mode).permitted == (not blocked)
        assert R.gate(r, principal=p, mode=mode, hide_blocked=False).permitted
    elif p.is_agent:
        assert v.permitted == (state == "cleared")
        if mode == "package":
            assert R.gate(r, principal=p, mode=mode, intended=USE, allow_restricted=True).permitted == (state in ("cleared", "restricted", "unknown"))
    else:
        assert v.permitted == (not blocked)  # people decide for themselves, except about blocked footage
    assert v.permitted == (not v.refusal)


def test_gate_takes_the_worst_combination_and_fails_closed():
    r = {**R.empty(), **RIGHTS_STATES["cleared"]}
    v = R.gate(r, mode="list", intended={"use": ["marketing", "editorial"], "channel": ["social", "broadcast"], "territory": ["GB", "US"]})
    assert v.verdict == "blocked" and any("broadcast" in x for x in v.reasons) and any("US" in x for x in v.reasons)
    bad = R.gate({**r, "expires": "not a date"}, mode="media")
    assert not bad.permitted and bad.blocked
    assert R.summary_status({"status": "restricted", "expires": "2001-01-01"}) == "expired"
    assert R.summary_status({"status": "restricted", "expires": "2099-01-01"}) == "restricted"
    with pytest.raises(ValueError):
        R.gate(r, mode="download")
    # A malformed date from the caller is the caller's error, not a blocked record (same as check_rights).
    with pytest.raises(ValueError):
        R.gate(r, mode="list", intended={"use": "marketing", "date": "2026-1-5"})
    with pytest.raises(ValueError):
        R.check(r, "marketing", on="2026-1-5")
    assert R.gate(r, mode="list", intended={"use": "marketing", "date": "2026-01-05"}).permitted


# ---------------------------------------------------------------------- search
@pytest.mark.parametrize("who", (*PEOPLE, *AGENTS))
def test_search_hides_blocked_footage_by_default(m, principals, who):
    res = m["lib"].search(principals[who], {"q": "", "limit": 200, "facets": False})
    got = set(_uids(res))
    assert got and not got & m["blocked"]
    assert got == set(m["state_of"]) - m["blocked"]
    assert res["hidden_blocked"] == len(m["blocked"]) == res["excluded_by_rights"]


@pytest.mark.parametrize("who", ("viewer", "agent"))
def test_search_shows_blocked_footage_as_blocked_when_asked(m, principals, who):
    res = m["lib"].search(principals[who], {"q": "", "limit": 200, "facets": False, "hide_blocked": False})
    assert set(_uids(res)) == set(m["state_of"]) and res["hidden_blocked"] == 0
    for r in res["results"]:
        if r["uid"] in m["blocked"]:
            assert r["rights"]["verdict"] == "blocked" and r["rights"]["reasons"]
            assert r["rights_badge"] in R.BLOCKED_BADGES


@pytest.mark.parametrize("who", ("viewer", "agent"))
@pytest.mark.parametrize("hide_blocked", (True, False))
def test_search_with_an_intended_use_returns_only_allowed_unless_asked(m, principals, who, hide_blocked):
    lib, p = m["lib"], principals[who]
    res = lib.search(p, {"q": "", "limit": 200, "facets": False, "intended_use": USE, "hide_blocked": hide_blocked})
    assert set(_uids(res)) == set(m["by_state"]["cleared"])
    assert all(r["rights"]["verdict"] == "allowed" for r in res["results"])
    res = lib.search(p, {"q": "", "limit": 200, "facets": False, "hide_blocked": hide_blocked,
                         "intended_use": {**USE, "include": ["allowed", "unknown", "blocked"]}})
    got = {r["uid"]: r["rights"]["verdict"] for r in res["results"]}
    for uid, verdict in got.items():
        assert verdict == VERDICT_FOR_USE[m["state_of"][uid]]
    # Blocked for every use (not cleared, expired) stays hidden while hide_blocked is on, whatever `include` says.
    assert bool(set(got) & m["blocked"]) == (not hide_blocked)
    assert set(m["by_state"]["editorial_only"]) <= set(got)  # blocked for this use only: listed when asked for


def test_search_paging_never_leaks_blocked_footage(m, principals):
    lib, p, seen, cursor = m["lib"], principals["agent"], [], None
    while True:
        res = lib.search(p, {"q": "", "limit": 2, "cursor": cursor, "facets": False})
        seen += _uids(res)
        cursor = res["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) and set(seen) == set(m["state_of"]) - m["blocked"]


# ---------------------------------------------------------------------- similar
@pytest.fixture()
def fake_encoder(monkeypatch):
    from metachlorian.media import siglip

    class Enc:
        def encode_images(self, images, batch=8):
            return np.ones((len(images), 8), np.float32)

    monkeypatch.setattr(siglip, "load", lambda root: Enc())


@pytest.mark.parametrize("by", ("shot", "image", "clip"))
@pytest.mark.parametrize("who", ("viewer", "agent"))
def test_find_similar_applies_the_same_rule(m, principals, fake_encoder, tmp_path, by, who):
    import cv2

    lib, p = m["lib"], principals[who]
    if by == "shot":
        kw = {"shot_uid": m["by_state"]["unknown"][0]}
    elif by == "image":
        kw = {"image": cv2.imencode(".png", np.full((32, 32, 3), 128, np.uint8))[1].tobytes()}
    else:
        kw = {"clip": make_video(tmp_path / "query.mp4", segments=("testsrc2",), seg_s=1.0, audio=False)}
    res = lib.find_similar(p, limit=100, **kw)
    got = set(_uids(res))
    assert got and not got & m["blocked"]
    res = lib.find_similar(p, limit=100, intended=USE, **kw)
    assert set(_uids(res)) <= set(m["by_state"]["cleared"]) and all(r["rights"]["verdict"] == "allowed" for r in res["results"])
    res = lib.find_similar(p, limit=100, hide_blocked=False, **kw)
    assert set(_uids(res)) & m["blocked"]
    for r in res["results"]:
        assert (r.get("rights", {}).get("verdict") == "blocked") == (r["uid"] in m["blocked"])


# ---------------------------------------------------------------------- export_clip
@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("who", (*PEOPLE, *AGENTS))
def test_export_clip_rules(m, principals, state, who):
    lib, p = m["lib"], principals[who]
    shot = m["by_state"][state][0]
    if not p.can("media:export"):
        for mode in ("reference", *MEDIA_MODES):
            with pytest.raises(Forbidden, match="media:export"):
                lib.export_clip(p, shot, mode=mode, intended=USE)
        return
    # Reference (paths and timecodes, no media) is always available.
    assert "reference" in lib.export_clip(p, shot, mode="reference", intended=USE)
    for mode in MEDIA_MODES:
        allowed = state not in BLOCKED_STATES and (not p.is_agent or VERDICT_FOR_USE[state] == "allowed")
        if allowed:
            res = lib.export_clip(p, shot, mode=mode, intended=USE)
            assert Path(res["file"]).exists()
        else:
            before = _exports(m)
            with pytest.raises(Forbidden):
                lib.export_clip(p, shot, mode=mode, intended=USE)
            assert _exports(m) == before
        if p.is_agent and state == "cleared":
            # No intended use: the rights as recorded must be allowed, and they are (cleared, released).
            assert lib.export_clip(p, shot, mode=mode)


@pytest.mark.parametrize("who", ("editor", "agent+export"))
def test_export_clip_in_out_cannot_reach_a_blocked_neighbour(m, principals, who):
    """in/out are file seconds: naming an allowed shot must not cut the blocked shot next to it."""
    lib, p, db = m["lib"], principals[who], m["db"]
    shot0 = m["by_state"]["cleared"][0]
    nxt = db.q1("SELECT start_s, end_s FROM shots WHERE uid=?", (m["override"],))
    before = _exports(m)
    for a, b in ((nxt["start_s"], nxt["end_s"]), (0.0, nxt["end_s"]), (nxt["start_s"] - 0.2, nxt["start_s"] + 0.2)):
        for mode in MEDIA_MODES:
            with pytest.raises(Forbidden, match=m["override"]):
                lib.export_clip(p, shot0, a, b, mode=mode, intended=USE)
    assert _exports(m) == before
    assert "reference" in lib.export_clip(p, shot0, nxt["start_s"], nxt["end_s"], mode="reference", intended=USE)
    s0 = db.q1("SELECT start_s, end_s FROM shots WHERE uid=?", (shot0,))
    assert Path(lib.export_clip(p, shot0, s0["start_s"] + 0.1, s0["end_s"] - 0.1, mode="proxy", intended=USE)["file"]).exists()


def test_package_handles_stop_at_a_blocked_neighbour(m, principals):
    from metachlorian.media import ffmpeg

    db = m["db"]
    shot0 = db.q1("SELECT start_s, end_s FROM shots WHERE uid=?", (m["by_state"]["cleared"][0],))
    for who in ("editor", "agent+export"):
        res = m["lib"].build_package(principals[who], [{"shot_uid": m["by_state"]["cleared"][0]}], name=f"handles {who}",
                                     target={"usage": ["marketing"], "channels": ["paid_social"], "territories": ["GB"]})
        dur = float(ffmpeg.technical_metadata(Path(res["path"], "media", "it_01.mp4"))["duration"])
        assert dur <= shot0["end_s"] - shot0["start_s"] + 0.1, (who, dur)  # no handle into the not-cleared shot
    # A permitted neighbour still gives handles: the unknown file's first shot, for a person.
    u = db.q1("SELECT start_s, end_s FROM shots WHERE uid=?", (m["by_state"]["unknown"][0],))
    res = m["lib"].build_package(principals["editor"], [{"shot_uid": m["by_state"]["unknown"][0]}], name="handles ok")
    assert float(ffmpeg.technical_metadata(Path(res["path"], "media", "it_01.mp4"))["duration"]) > u["end_s"] - u["start_s"] + 0.5


def test_media_exports_ignore_the_callers_date(principals):
    """Media leaves today: asking about a date when the licence will be valid does not release it now."""
    r = {**R.empty(), **RIGHTS_STATES["cleared"], "starts": "2090-01-01"}
    later = {"use": "editorial", "date": "2091-01-01"}
    assert R.gate(r, mode="list", intended=later).permitted  # listing for a future use is fine
    for mode in ("media", "package"):
        v = R.gate(r, principal=principals["agent+export"], mode=mode, intended=later)
        assert not v.permitted and "starts" in v.refusal


def test_refused_exports_are_audited(m, principals):
    db = m["db"]
    with pytest.raises(Forbidden):
        m["lib"].export_clip(principals["editor"], m["override"], mode="proxy")
    row = db.q1("SELECT * FROM audit_log WHERE action='export_clip' AND actor='ed' ORDER BY id DESC LIMIT 1")
    assert json.loads(row["detail"])["refused"] == "blocked"


# ---------------------------------------------------------------------- build_package
@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("who", (*PEOPLE, *AGENTS))
def test_build_package_rules(m, principals, state, who):
    lib, p = m["lib"], principals[who]
    items = [{"shot_uid": m["by_state"][state][0]}]
    target = {"consumer": "generic", "usage": [USE["use"]], "channels": [USE["channel"]], "territories": [USE["territory"]]}
    before = _exports(m)
    if not p.can("media:export"):
        with pytest.raises(Forbidden, match="media:export"):
            lib.build_package(p, items, name="x", target=target, media_policy="none")
        assert _exports(m) == before
        return
    allowed = state not in BLOCKED_STATES and (not p.is_agent or VERDICT_FOR_USE[state] == "allowed")
    if allowed:
        res = lib.build_package(p, items, name=f"{who} {state}", target=target, media_policy="none")
        assert Path(res["path"], "manifest.json").exists() and res["verdict"] == VERDICT_FOR_USE[state]
    else:
        # Refused before anything is written: no package directory, no staging directory, no zip.
        with pytest.raises(Forbidden, match="refused"):
            lib.build_package(p, items, name=f"{who} {state}", target=target, media_policy="proxies", zip_it=True)
        assert _exports(m) == before
    if p.is_agent:
        # allow_restricted lets an agent through with restricted or unknown items, never blocked ones.
        ok = state not in BLOCKED_STATES and VERDICT_FOR_USE[state] != "blocked"
        if ok:
            assert lib.build_package(p, items, name="r", target=target, media_policy="none", allow_restricted=True)["verdict"]
        else:
            with pytest.raises(Forbidden):
                lib.build_package(p, items, name="r", target=target, media_policy="none", allow_restricted=True)


def test_one_blocked_shot_refuses_the_whole_package_and_names_it(m, principals):
    before = _exports(m)
    items = [{"shot_uid": u} for u in m["by_state"]["cleared"] + m["by_state"]["override"]]
    with pytest.raises(Forbidden, match=m["override"]):
        m["lib"].build_package(principals["editor"], items, name="mixed", media_policy="proxies", zip_it=True)
    assert _exports(m) == before


def test_package_media_for_allowed_shots(m, principals):
    res = m["lib"].build_package(principals["agent+export"], [{"shot_uid": m["by_state"]["cleared"][0]}], name="ok",
                                 target={"usage": ["marketing"], "channels": ["paid_social"], "territories": ["GB"]}, zip_it=True)
    assert res["verdict"] == "allowed" and Path(res["zip"]).exists()
    assert any(p.suffix == ".mp4" for p in Path(res["path"], "media").iterdir())


# ---------------------------------------------------------------------- /media
def test_media_route(m):
    s, db = m["settings"], m["db"]
    tokens = {}
    for role in ("viewer", "agent"):
        uid = A.create_user(db, f"media-{role}", role, None if role == "agent" else "correct horse battery")
        tokens[role] = A.create_token(db, uid, "t")
    s.require_auth = True
    try:
        with TestClient(__import__("metachlorian.api.app", fromlist=["create_app"]).create_app(s, db, start_workers=False)) as c:
            for state, auid in m["assets"].items():
                # The cleared file holds the overridden (not cleared) shot, so its whole-file media is held back from agents.
                blocked_file = state in ("not_cleared", "expired", "cleared")
                # Video needs every shot cleared as recorded (as export_clip without a use); stills only no blocked shot.
                agent_ok = {"proxy.mp4": state == "editorial_only", "poster.jpg": not blocked_file}
                for path, ok in agent_ok.items():
                    url = f"/media/{auid}/{path}"
                    assert c.get(url, headers={"Authorization": f"Bearer {tokens['viewer']}"}).status_code == 200, url
                    r = c.get(url, headers={"Authorization": f"Bearer {tokens['agent']}"})
                    assert r.status_code == (200 if ok else 403), (url, r.status_code)
                    assert c.get(f"{url}?token={tokens['agent']}").status_code == (200 if ok else 403)
                assert c.get(f"/media/{auid}/proxy.mp4").status_code == 401
                # An id that is not in the library never reaches the file system for agents (case-insensitive disks).
                assert c.get(f"/media/{auid.upper()}/poster.jpg", headers={"Authorization": f"Bearer {tokens['agent']}"}).status_code == 404
            assert c.get("/media/nope/proxy.mp4", headers={"Authorization": f"Bearer {tokens['agent']}"}).status_code == 404
    finally:
        s.require_auth = False


# ---------------------------------------------------------------------- MCP
def _tool_args(m) -> dict[str, dict]:
    shot, asset = m["by_state"]["cleared"][0], m["assets"]["cleared"]
    return {
        "search_shots": {"query": ""}, "get_shot": {"shot_id": shot}, "get_asset": {"asset_id": asset},
        "find_similar": {"shot_id": shot}, "check_rights": {"shot_ids": [shot]},
        "export_clip": {"shot_id": shot, "mode": "reference"}, "build_package": {"name": "x", "items": [{"shot_uid": shot}], "media": "none"},
        "library_stats": {}, "list_folders": {}, "list_files": {}, "get_collection": {"collection_id": "nope"}, "list_people": {},
        "list_vocabularies": {}, "list_collections": {},
        "correct_tag": {"shot_id": shot, "field": "camera.movement", "note": "test", "add": ["handheld"]},
    }


NEEDS = {"export_clip": "media:export", "build_package": "media:export", "correct_tag": "tags:write"}


@pytest.mark.parametrize("scopes", ("none", "agent"))
def test_every_mcp_tool_errors_without_its_scope(m, mcp_client, scopes):
    p = Principal(9, "scopeless", "agent", set() if scopes == "none" else set(A.AGENT_DEFAULT), "mcp")
    args = _tool_args(m)

    async def go():
        async with mcp_client(m["lib"], p) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert names == set(args), "add new tools to _tool_args so their scope is tested"
            return {name: await c.call_tool(name, a) for name, a in args.items()}

    out = anyio.run(go)
    for name, res in out.items():
        scope = NEEDS.get(name, "library:read")
        if scope in p.scopes:
            continue
        assert res.is_error, name
        assert scope in res.content[0].text, (name, res.content[0].text)


def test_mcp_exits_follow_the_gate(m, mcp_client, principals):
    async def go():
        async with mcp_client(m["lib"], principals["agent+export"]) as c:
            search = await c.call_tool("search_shots", {"query": "", "limit": 100})
            similar = await c.call_tool("find_similar", {"shot_id": m["by_state"]["unknown"][0], "limit": 100})
            exp = {st: await c.call_tool("export_clip", {"shot_id": m["by_state"][st][0], "mode": "proxy", "intended_use": USE}) for st in STATES}
            pkg = {st: await c.call_tool("build_package", {"name": st, "items": [{"shot_uid": m["by_state"][st][0]}], "media": "none",
                                                           "usage": ["marketing"], "channels": ["paid_social"], "territories": ["GB"]})
                   for st in STATES}
            return search, similar, exp, pkg

    search, similar, exp, pkg = anyio.run(go)
    for res in (search, similar):
        assert not res.is_error
        uids = {r["uid"] for r in json.loads(res.content[0].text)["results"]}
        assert uids and not uids & m["blocked"]
    for st in STATES:
        assert exp[st].is_error == (st != "cleared"), (st, exp[st].content[0].text)
        assert pkg[st].is_error == (st != "cleared"), (st, pkg[st].content[0].text)


# ---------------------------------------------------------------------- /api/exports/file
def test_export_downloads_recheck_rights_and_agents_get_only_their_own(processed):
    from metachlorian.api.app import create_app

    s, db, a = processed
    R.set_rights(db, a["id"], {"status": "cleared", "model_release": "not_applicable"}, "x")
    ed = A.create_token(db, A.create_user(db, "ed", "editor", "correct horse battery"), "t")
    bot_uid = A.create_user(db, "bot", "agent")
    bot = A.create_token(db, bot_uid, "t", ["library:read", "media:export"])
    bot2 = A.create_token(db, A.create_user(db, "bot2", "agent"), "t", ["library:read", "media:export"])
    shot = db.q1("SELECT uid FROM shots WHERE asset_id=? ORDER BY idx", (a["id"],))["uid"]
    s.require_auth = True
    H = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731
    with TestClient(create_app(s, db, start_workers=False)) as c:
        clip = c.post("/api/export/clip", json={"shot_uid": shot, "mode": "proxy"}, headers=H(ed)).json()["download"]
        mine = c.post("/api/export/clip", json={"shot_uid": shot, "mode": "edl"}, headers=H(bot)).json()["download"]
        pkg = c.post("/api/package", json={"items": [{"shot_uid": shot}], "name": "p", "zip": True}, headers=H(ed)).json()
        assert c.get(clip, headers=H(ed)).status_code == 200
        assert c.get(mine, headers=H(bot)).status_code == 200
        assert c.get(mine, headers=H(bot2)).status_code == 403  # another agent's export
        assert c.get(clip, headers=H(bot)).status_code == 403  # a person's export
        for url in (pkg["download"], pkg["download"] + ".zip", pkg["download"] + "/media/it_01.mp4"):
            assert c.get(url, headers=H(ed)).status_code == 200, url
        # Files without a record (made outside the service): people only.
        (s.export_dir / "legacy.txt").write_text("x")
        assert c.get("/api/exports/file?path=legacy.txt", headers=H(ed)).status_code == 200
        assert c.get("/api/exports/file?path=legacy.txt", headers=H(bot)).status_code == 403
        # The records and staging folders are not downloadable.
        assert c.get("/api/exports/file?path=.rights", headers=H(ed)).status_code == 404
        assert c.get("/api/exports/file?path=../lib.sqlite", headers=H(ed)).status_code == 400
        # Rights change after the export: nothing already exported leaves any more.
        R.set_rights(db, a["id"], {"status": "not_cleared"}, "x")
        for url in (clip, mine, pkg["download"], pkg["download"] + ".zip", pkg["download"] + "/media/it_01.mp4"):
            who = bot if url == mine else ed
            assert c.get(url, headers=H(who)).status_code == 403, url
    s.require_auth = False
