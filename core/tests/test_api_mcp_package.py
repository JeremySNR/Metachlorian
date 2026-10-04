import json

import anyio
import opentimelineio as otio
import pytest
from fastapi.testclient import TestClient

from metachlorian import auth as A
from metachlorian import rights as R
from metachlorian.api.app import create_app
from metachlorian.exports.package import build_package, validate_manifest
from metachlorian.indexer import index_asset
from metachlorian.ingest.scan import add_source, scan_source

from .test_ingest_pipeline import run_all


@pytest.fixture()
def processed(lib, footage):
    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    run_all(s, db)
    a = db.q1("SELECT * FROM assets")
    index_asset(db, s, a["id"])
    return s, db, a


def test_package_validates_and_timelines_parse(processed):
    s, db, a = processed
    R.set_rights(db, a["id"], {"status": "cleared", "permitted_uses": ["marketing"], "channels": ["social"], "territories": ["GB"],
                               "model_release": "not_applicable"}, "x")
    uids = [r["uid"] for r in db.q("SELECT uid FROM shots WHERE asset_id=? ORDER BY idx", (a["id"],))]
    items = [{"shot_uid": uids[0], "role": "interview"}, {"shot_uid": uids[1]}, {"shot_uid": uids[2], "in": 4.2, "out": 5.5}]
    res = build_package(db, s, items, "Test package", "brief", {"consumer": "cutawan", "aspect": "9:16", "usage": ["marketing"],
                                                                "channels": ["organic_social"], "territories": ["GB"]})
    m = res["manifest"]
    assert validate_manifest(m) == []
    assert res["verdict"] == "allowed"
    assert m["cutawan"]["mode"] == "a_roll_with_inserts" and len(m["cutawan"]["inserts"]) == 2
    from pathlib import Path

    root = Path(res["path"])
    assert (root / "manifest.json").exists() and (root / "RIGHTS.md").exists() and (root / "checksums.sha256").exists()
    tl = otio.adapters.read_from_file(str(root / "timelines/seq_main.otio"))
    assert len(tl.video_tracks()) == 2
    edl = (root / "timelines/seq_main.edl").read_text()
    assert "001  " in edl and "FCM: NON-DROP FRAME" in edl
    assert (root / "timelines/seq_main.fcpxml").read_text().startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>')
    # Trimmed item: source range reflects in/out.
    it3 = next(i for i in m["items"] if i["item_id"] == "it_03")
    assert it3["source_range"]["in"]["seconds"] == 4.2


def test_package_rejects_bad_in_out(processed):
    s, db, a = processed
    uid = db.q1("SELECT uid FROM shots WHERE asset_id=? ORDER BY idx", (a["id"],))["uid"]
    with pytest.raises(ValueError):
        build_package(db, s, [{"shot_uid": uid, "in": 0.0, "out": 99.0}], "bad")
    # Inserts over an A-roll need an A-roll item (was an IndexError -> HTTP 500).
    with pytest.raises(ValueError, match="A-roll"):
        build_package(db, s, [{"shot_uid": uid, "role": "broll"}], "no a-roll", media_policy="none", mode="a_roll_with_inserts")


def _team_app(s, db):
    s.require_auth = True
    return TestClient(create_app(s, db, start_workers=False))


def test_api_auth_roles_and_csrf(processed):
    s, db, a = processed
    A.create_user(db, "admin", "admin", "correct horse battery")
    A.create_user(db, "viewer", "viewer", "correct horse battery")
    with _team_app(s, db) as c:
        assert c.get("/api/library/stats").status_code == 401
        assert c.post("/api/auth/login", json={"username": "viewer", "password": "wrong password!"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "viewer", "password": "correct horse battery"}).status_code == 200
        assert c.get("/api/library/stats").status_code == 200
        # Cookie-authenticated writes need the custom header (CSRF defence)...
        assert c.post("/api/collections", json={"name": "x"}).status_code == 403
        # ...and a viewer cannot write at all.
        r = c.post("/api/collections", json={"name": "x"}, headers={"X-Metachlorian": "1"})
        assert r.status_code == 403 and "collections:write" in r.json()["detail"]
    # Agent tokens: read-only by default, never rights or admin.
    uid = A.create_user(db, "bot", "agent")
    tok = A.create_token(db, uid, "t")
    with pytest.raises(ValueError):
        A.create_token(db, uid, "t2", ["rights:write"])
    with _team_app(s, db) as c:
        h = {"Authorization": f"Bearer {tok}"}
        assert c.post("/api/search", json={"q": ""}, headers=h).status_code == 200
        shot = db.q1("SELECT uid FROM shots LIMIT 1")["uid"]
        assert c.post("/api/export/clip", json={"shot_uid": shot}, headers=h).status_code == 403
        assert c.put(f"/api/rights/{a['uid']}", json={"status": "cleared"}, headers=h).status_code == 403
        assert c.get("/api/admin/audit", headers=h).status_code == 403
    actions = [r["action"] for r in db.q("SELECT action FROM audit_log WHERE actor='bot'")]
    assert "search_shots" in actions  # every agent action is logged


def test_solo_mode_rejects_foreign_host(processed):
    s, db, a = processed
    s.require_auth = False
    with TestClient(create_app(s, db, start_workers=False), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as c:
        assert c.get("/api/library/stats").status_code == 200
        assert c.get("/api/library/stats", headers={"Host": "attacker.example"}).status_code == 401
        assert c.post("/api/collections", json={"name": "x"}).status_code == 403
        assert c.post("/api/collections", json={"name": "x"}, headers={"X-Metachlorian": "1"}).status_code == 200


def test_mcp_tools_respect_scopes(processed):
    s, db, a = processed
    from metachlorian.mcp_server.server import build_server, stdio_principal
    from metachlorian.service import Library

    lib = Library(db, s)
    server = build_server(lib)
    stdio_principal.set(A.Principal(None, "local-agent", "agent", set(A.AGENT_DEFAULT), "mcp"))
    shot = db.q1("SELECT uid FROM shots LIMIT 1")["uid"]

    async def go():
        tools = await server.list_tools()
        names = {t.name for t in tools}
        assert {"search_shots", "get_shot", "get_asset", "find_similar", "check_rights", "export_clip", "build_package", "library_stats"} <= names
        res = await server.call_tool("search_shots", {"query": "", "limit": 2})
        return res, await server.call_tool("export_clip", {"shot_id": shot, "mode": "proxy"})

    res, exp = anyio.run(go)
    text = json.dumps(res, default=str)
    assert "results" in text
    assert "media:export" in json.dumps(exp, default=str)  # read-only agent refused
