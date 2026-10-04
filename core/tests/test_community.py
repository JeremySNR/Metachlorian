"""Privacy boundary and durable publisher behaviour; network is always replaced with test transports."""
import json
import subprocess

import httpx
import pytest

from metachlorian.community import publisher, public
from metachlorian.community.protocol import Contribution, validate_endpoint
from metachlorian.config import Settings, load_settings
from metachlorian.db import dumps, now
from metachlorian.ingest.scan import content_hash, register_file
from metachlorian.runtime import save_settings

VIDEO = "abcdefghijk"


@pytest.fixture
def ready(lib, tmp_path):
    settings, db = lib
    path = tmp_path / "personal-looking-name.mp4"
    path.write_bytes(b"public downloaded video stand-in")
    _, aid = register_file(db, path)
    db.x("UPDATE assets SET status='ready', duration=20 WHERE id=?", (aid,))
    sid = db.x("INSERT INTO shots(uid,asset_id,idx,start_s,end_s,start_frame,end_frame,segmenter) VALUES('shot-test',?,0,0,20,0,500,'shots@1')", (aid,)).lastrowid
    db.x("INSERT INTO signals(level,target_id,asset_id,name,value,source,confidence,model_version,created_at)"
         " VALUES('shot',?,?,'content.caption',?,'fusion',0.8,'1',?)", (sid, aid, dumps({"value": "Coastal drone sunset"}), now()))
    return settings, db, aid, sid, path


def enroll(ready, availability="public", site="Youtube"):
    settings, db, aid, _, _ = ready
    publisher.enroll(db, settings, aid, site, {"id": VIDEO, "availability": availability})


@pytest.mark.parametrize("availability", [None, "unlisted", "private", "subscriber_only", "needs_auth", "premium_only"])
def test_nonpublic_and_unknown_downloads_never_enroll(ready, availability):
    enroll(ready, availability)
    assert ready[1].q("SELECT * FROM community_outbox") == []


def test_default_opt_out_and_no_backfill(ready):
    settings, db, *_ = ready
    assert Settings().community_enabled is True
    settings.community_enabled = False
    enroll(ready)
    settings.community_enabled = True
    assert publisher.build_contribution(db, ready[2]) is None
    enroll(ready)
    assert publisher.build_contribution(db, ready[2]) is not None
    save_settings(settings, {"community_enabled": False})
    assert load_settings(settings.data_dir).community_enabled is False
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"
    save_settings(settings, {"community_enabled": True})
    assert publisher.build_contribution(db, ready[2]) is None


def test_local_files_other_sites_and_changed_bytes_are_excluded(ready, monkeypatch):
    settings, db, aid, _, path = ready
    assert publisher.build_contribution(db, aid) is None  # local scanned file is not in the outbox
    enroll(ready, site="Vimeo")
    assert publisher.build_contribution(db, aid) is None
    enroll(ready)
    settings.community_url = "https://community.example"
    path.write_bytes(b"personal footage that replaced the downloaded file")
    monkeypatch.setattr(publisher, "verify_public", lambda *a: pytest.fail("changed bytes must never reach a public probe"))
    assert publisher.sync_once(db, settings) == 0
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"


def test_payload_allowlist_excludes_private_fields_notes_names_and_paths(ready):
    settings, db, aid, sid, path = ready
    for name, source, value in [("people.identities", "fusion", {"name": "PRIVATE PERSON"}), ("content.place", "rollup", {"gps": "PRIVATE GPS"}),
                                ("vlm.error", "fusion", "PRIVATE ERROR"), ("content.caption", "human", "PRIVATE CORRECTION"),
                                ("tags", "fusion", ["PRIVATE TAG"]), ("origin", "import", {"path": str(path)})]:
        db.x("INSERT INTO signals(level,target_id,asset_id,name,value,source,confidence,model_version,created_at)"
             " VALUES('shot',?,?,?,?,?,1,'1',?)", (sid, aid, name, dumps(value), source, now()))
    db.x("INSERT INTO corrections(level,asset_uid,shot_uid,field,op,value,note,actor,created_at) VALUES('shot','a','shot-test','content.caption','set',?,?,'PRIVATE USER',?)",
         (dumps("PRIVATE CAPTION"), "PRIVATE NOTE", now()))
    enroll(ready)
    body = publisher.build_contribution(db, aid).model_dump_json()
    assert "Coastal drone sunset" in body
    assert "PRIVATE" not in body and str(path) not in body and "personal-looking" not in body
    assert "asset_id" not in body and "shot-test" not in body


def test_sync_retries_deduplicates_and_updates_analysis(ready, monkeypatch):
    settings, db, aid, sid, _ = ready
    enroll(ready)
    settings.community_url = "https://community.example"
    monkeypatch.setattr(publisher, "verify_public", lambda *a: {})
    calls = []
    def receive(request):
        calls.append(json.loads(request.content))
        return httpx.Response(503 if len(calls) == 1 else 200, json={"status": "stored"})
    transport = httpx.MockTransport(receive)
    assert publisher.sync_once(db, settings, transport) == 0
    assert db.q1("SELECT attempts FROM community_outbox")[0] == 1
    db.x("UPDATE community_outbox SET run_after=0")
    assert publisher.sync_once(db, settings, transport) == 1
    db.x("UPDATE community_outbox SET run_after=0")
    assert publisher.sync_once(db, settings, transport) == 0 and len(calls) == 2
    db.x("UPDATE signals SET value=? WHERE target_id=? AND name='content.caption'", (dumps("Ocean waves"), sid))
    db.x("UPDATE community_outbox SET run_after=0")
    assert publisher.sync_once(db, settings, transport) == 1
    assert calls[-1]["shots"][0]["fields"]["content.caption"]["value"] == "Ocean waves"


def test_opt_out_during_visibility_probe_sends_nothing(ready, monkeypatch):
    settings, db, *_ = ready
    enroll(ready)
    settings.community_url = "https://community.example"
    def probe(*a):
        save_settings(settings, {"community_enabled": False})
        return {}
    monkeypatch.setattr(publisher, "verify_public", probe)
    transport = httpx.MockTransport(lambda r: pytest.fail("opt-out must prevent POST"))
    assert publisher.sync_once(db, settings, transport) == 0


def test_replacement_during_probe_and_service_rejection_stop_sharing(ready, monkeypatch):
    settings, db, _, _, path = ready
    enroll(ready)
    settings.community_url = "https://community.example"
    original = path.read_bytes()
    def probe(*a):
        path.write_bytes(b"replaced with personal footage during public visibility check")
        return {}
    monkeypatch.setattr(publisher, "verify_public", probe)
    assert publisher.sync_once(db, settings, httpx.MockTransport(lambda r: pytest.fail("changed file must not POST"))) == 0
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"
    path.write_bytes(original)
    db.x("UPDATE community_outbox SET status='pending'")
    monkeypatch.setattr(publisher, "verify_public", lambda *a: {})
    assert publisher.sync_once(db, settings, httpx.MockTransport(lambda r: httpx.Response(403))) == 0
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"


@pytest.mark.parametrize("response_code", [200, 503])
def test_inflight_response_cannot_restore_opted_out_queue(ready, monkeypatch, response_code):
    settings, db, *_ = ready
    enroll(ready)
    settings.community_url = "https://community.example"
    monkeypatch.setattr(publisher, "verify_public", lambda *a: {})
    def receive(request):
        save_settings(settings, {"community_enabled": False})
        return httpx.Response(response_code)
    publisher.sync_once(db, settings, httpx.MockTransport(receive))
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"


def test_processing_deletion_and_replaced_library_records_never_publish(ready):
    settings, db, aid, *_ = ready
    enroll(ready)
    for sql in ["UPDATE assets SET status='processing'", "UPDATE assets SET status='ready', deleted_at=1",
                "UPDATE assets SET deleted_at=NULL, content_hash='changed'"]:
        db.x(sql)
        assert publisher.build_contribution(db, aid) is None


def test_visibility_probe_never_uses_cookies_config_or_plugins(ready, monkeypatch):
    settings, *_ = ready
    settings.import_cookies_browser = "chrome"
    (settings.data_dir / "import-cookies.txt").write_text("PRIVATE COOKIE")
    monkeypatch.setattr(public.ytdlp, "find", lambda _: "yt-dlp")
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps({"id": VIDEO, "extractor_key": "Youtube", "availability": "public"}), "")
    monkeypatch.setattr(public.subprocess, "run", run)
    public.verify_public(VIDEO, settings)
    args = calls[0]
    assert "--ignore-config" in args and "--no-plugin-dirs" in args
    assert not any("cookie" in x or "chrome" in x for x in args)
    assert args[-1] == f"https://www.youtube.com/watch?v={VIDEO}"


@pytest.mark.parametrize("value", ["http://remote.example", "https://user:pass@example.com", "https://example.com?token=secret", "file:///tmp/db"])
def test_unsafe_endpoints_are_rejected(value):
    with pytest.raises(ValueError):
        validate_endpoint(value)


def test_egress_reports_community_separately_from_model_adapters():
    settings = Settings(community_url="https://community.example")
    egress = settings.egress_summary()
    assert egress["content_leaves_machine"] and egress["adapters"] == [] and egress["community"]["active"]
    settings.community_enabled = False
    assert not settings.egress_summary()["content_leaves_machine"]


def test_environment_opt_out_suppresses_existing_queue(ready, monkeypatch):
    settings, db, *_ = ready
    enroll(ready)
    monkeypatch.setenv("METACHLORIAN_COMMUNITY_ENABLED", "false")
    settings = load_settings(settings.data_dir)
    assert publisher.sync_once(db, settings) == 0
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"


def test_api_community_search_requires_read_scope_and_never_reads_library(ready, monkeypatch):
    from fastapi.testclient import TestClient
    from metachlorian import auth
    from metachlorian.api.app import create_app

    settings, db, *_ = ready
    settings.require_auth = True
    user = auth.create_user(db, "community-reader", "agent")
    allowed = auth.create_token(db, user, "read", ["library:read"])
    denied = auth.create_token(db, user, "other", ["media:export"])
    calls = []
    def search(settings, query, limit, offset):
        calls.append((query, limit, offset))
        return {"results": [], "next_offset": None, "query": query, "hidden_pending_visibility": 0}
    monkeypatch.setattr(publisher, "search", search)
    with TestClient(create_app(settings, db, start_workers=False)) as client:
        assert client.get("/api/community/status").status_code == 401
        assert client.get("/api/community/search?q=coast", headers={"Authorization": "Bearer " + denied}).status_code == 403
        assert calls == []
        headers = {"Authorization": "Bearer " + allowed}
        assert client.get("/api/community/search?q=coast", headers=headers).json()["results"] == []
        assert calls == [("coast", 20, 0)]
        assert client.get("/api/community/status", headers=headers).status_code == 200
        assert client.get("/api/community/search?limit=100", headers=headers).status_code == 422
        assert client.put("/api/admin/settings", json={"community_enabled": False}, headers=headers).status_code == 403
