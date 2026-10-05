"""Privacy boundary and durable publisher behaviour; network is always replaced with test transports."""
import json

import httpx
import pytest

from metachlorian.community import publisher
from metachlorian.community.protocol import Contribution, validate_endpoint
from metachlorian.config import Settings, load_settings
from metachlorian.db import dumps, now
from metachlorian.ingest import scan
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
def test_youtube_downloads_enroll_without_visibility_checks(ready, availability):
    enroll(ready, availability)
    assert ready[1].q1("SELECT video_id FROM community_outbox")[0] == VIDEO


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


def test_many_machine_terms_are_bounded_before_publishing(ready):
    settings, db, aid, sid, _ = ready
    terms = [{"term": f"object-{i}"} for i in range(31)]
    db.x("INSERT INTO signals(level,target_id,asset_id,name,value,source,confidence,model_version,created_at)"
         " VALUES('shot',?,?,'content.objects',?,'fusion',0.8,'1',?)", (sid, aid, dumps(terms), now()))
    enroll(ready)
    settings.community_url = "https://community.example"
    received = []
    def receive(request):
        received.append(json.loads(request.content))
        return httpx.Response(200)
    assert publisher.sync_once(db, settings, httpx.MockTransport(receive)) == 1
    assert received[0]["shots"][0]["fields"]["content.objects"]["value"] == [f"object-{i}" for i in range(30)]


@pytest.mark.parametrize("invalid", ["shots", "moments", "moment_text", "moment_span"])
def test_invalid_analysis_is_suppressed_without_network_or_retries(ready, invalid):
    settings, db, aid, _, _ = ready
    with db.tx() as conn:
        if invalid == "shots":
            conn.executemany("INSERT INTO shots(uid,asset_id,idx,start_s,end_s,start_frame,end_frame,segmenter)"
                             " VALUES(?,?,?,0,20,0,500,'shots@1')",
                             [(f"extra-{i}", aid, i + 1) for i in range(2000)])
        else:
            count = 4001 if invalid == "moments" else 1
            text = "PRIVATE" * 2001 if invalid == "moment_text" else "Transcript"
            end = 0 if invalid == "moment_span" else 20
            conn.executemany("INSERT INTO moments(asset_id,kind,start_s,end_s,text,source,model_version)"
                             " VALUES(?,'speech',0,?,?,'speech','1')", [(aid, end, text)] * count)
    enroll(ready)
    settings.community_url = "https://community.example"
    transport = httpx.MockTransport(lambda r: pytest.fail("invalid analysis must never POST"))
    assert publisher.sync_once(db, settings, transport) == 0
    job = db.q1("SELECT * FROM community_outbox")
    assert job["status"] == "suppressed" and job["attempts"] == 0
    assert job["message"] == "Analysis does not meet community contribution limits"
    assert publisher.sync_once(db, settings, transport) == 0
    assert db.q1("SELECT attempts FROM community_outbox")[0] == 0


def test_unfinished_analysis_cannot_starve_later_contributions(ready, tmp_path, monkeypatch):
    settings, db, aid, *_ = ready
    settings.community_url = "https://community.example"
    # Fill a whole batch with older downloads that have no useful analysis yet.
    for i in range(5):
        path = tmp_path / f"unfinished-{i}.mp4"
        path.write_bytes(f"unfinished public download {i}".encode())
        _, waiting = register_file(db, path)
        db.x("UPDATE assets SET status='ready' WHERE id=?", (waiting,))
        publisher.enroll(db, settings, waiting, "Youtube", {"id": VIDEO, "availability": "public"})
        db.x("UPDATE community_outbox SET updated_at=0 WHERE asset_id=?", (waiting,))
    enroll(ready)
    db.x("UPDATE community_outbox SET updated_at=1 WHERE asset_id=?", (aid,))
    received = []
    def receive(request):
        received.append(json.loads(request.content))
        return httpx.Response(200)
    transport = httpx.MockTransport(receive)
    assert publisher.sync_once(db, settings, transport) == 0
    assert publisher.sync_once(db, settings, transport) == 1
    assert len(received) == 1 and received[0]["shots"][0]["fields"]["content.caption"]["value"] == "Coastal drone sunset"


def test_opt_out_during_file_check_sends_nothing(ready, monkeypatch):
    settings, db, *_ = ready
    enroll(ready)
    settings.community_url = "https://community.example"
    def hash_file(path):
        digest = content_hash(path)
        save_settings(settings, {"community_enabled": False})
        return digest
    monkeypatch.setattr(scan, "content_hash", hash_file)
    transport = httpx.MockTransport(lambda r: pytest.fail("opt-out must prevent POST"))
    assert publisher.sync_once(db, settings, transport) == 0


def test_replacement_during_file_check_and_service_rejection_stop_sharing(ready, monkeypatch):
    settings, db, _, _, path = ready
    enroll(ready)
    settings.community_url = "https://community.example"
    original = path.read_bytes()
    def hash_file(file):
        digest = content_hash(file)
        path.write_bytes(b"personal footage replaced the downloaded file")
        return digest
    monkeypatch.setattr(scan, "content_hash", hash_file)
    assert publisher.sync_once(db, settings, httpx.MockTransport(lambda r: pytest.fail("changed file must not POST"))) == 0
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"
    path.write_bytes(original)
    db.x("UPDATE community_outbox SET status='pending'")
    monkeypatch.setattr(scan, "content_hash", content_hash)
    assert publisher.sync_once(db, settings, httpx.MockTransport(lambda r: httpx.Response(403))) == 0
    assert db.q1("SELECT status FROM community_outbox")[0] == "suppressed"


@pytest.mark.parametrize("response_code", [200, 503])
def test_inflight_response_cannot_restore_opted_out_queue(ready, monkeypatch, response_code):
    settings, db, *_ = ready
    enroll(ready)
    settings.community_url = "https://community.example"
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


def test_download_metadata_is_allowlisted_and_only_the_contribution_is_sent(ready, monkeypatch):
    from metachlorian.ingest.importer import _store_origin

    settings, db, aid, *_ = ready
    settings.community_url = "https://community.example"
    settings.import_cookies_browser = "chrome"
    (settings.data_dir / "import-cookies.txt").write_text("PRIVATE COOKIE")
    _store_origin(db, aid, {"title": "Imported YouTube title", "uploader": "YouTube channel", "license": "CC BY",
                           "description": "PRIVATE DESCRIPTION", "url": "https://example.com?token=PRIVATE", "tags": ["PRIVATE"]}, True)
    enroll(ready, availability="private")
    def receive(request):
        assert str(request.url) == "https://community.example/v1/contributions"
        assert "cookie" not in request.headers
        assert "PRIVATE" not in request.content.decode()
        data = json.loads(request.content)
        assert data["title"] == "Imported YouTube title" and data["channel"] == "YouTube channel"
        assert data["license"] == "CC BY" and data["duration"] == 20
        return httpx.Response(200)
    assert publisher.sync_once(db, settings, httpx.MockTransport(receive)) == 1


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
