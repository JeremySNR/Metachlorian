"""Authentication: the CSRF header rule, the solo-mode loopback rule, token expiry and revocation, and scopes
that never widen past the role."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metachlorian import auth as A
from metachlorian.api.app import create_app

PW = "correct horse battery"


def _app(s, db, require_auth=True, **kw):
    s.require_auth = require_auth
    return TestClient(create_app(s, db, start_workers=False), **kw)


def test_cookie_sessions_need_the_custom_header_for_writes(lib):
    s, db = lib
    A.create_user(db, "ed", "editor", PW)
    with _app(s, db) as c:
        assert c.post("/api/auth/login", json={"username": "ed", "password": PW}).status_code == 200  # login itself is exempt
        assert c.get("/api/collections").status_code == 200  # safe methods need nothing more
        assert c.post("/api/collections", json={"name": "x"}).status_code == 403
        assert c.post("/api/collections", json={"name": "x"}, headers={"X-Metachlorian": "0"}).status_code == 403
        assert c.post("/api/collections", json={"name": "x"}, headers={"X-Metachlorian": "1"}).status_code == 200
    # Bearer tokens are not sent by browsers on their own, so they need no header.
    tok = A.create_token(db, A.create_user(db, "ed2", "editor"), "cli")
    with _app(s, db) as c:
        assert c.post("/api/collections", json={"name": "y"}, headers={"Authorization": f"Bearer {tok}"}).status_code == 200


@pytest.mark.parametrize("client,host,ok", [
    ("127.0.0.1", "127.0.0.1", True),
    ("127.0.0.1", "localhost", True),
    ("::1", "[::1]", True),
    ("127.0.0.1", "attacker.example", False),   # DNS rebinding: a foreign Host reaching a loopback socket
    ("192.168.1.20", "127.0.0.1", False),       # another machine claiming a loopback Host
    ("192.168.1.20", "192.168.1.5", False),
])
def test_solo_mode_trusts_only_loopback_on_both_ends(lib, client, host, ok):
    s, db = lib
    with _app(s, db, require_auth=False, base_url="http://127.0.0.1", client=(client, 50000)) as c:
        r = c.get("/api/me", headers={"Host": host})
        assert (r.status_code == 200) == ok, (client, host, r.status_code)
        if ok:
            assert r.json()["role"] == "admin"
            # The local admin is browser-originated: writes still need the CSRF header.
            assert c.post("/api/collections", json={"name": "x"}, headers={"Host": host}).status_code == 403


def test_expired_revoked_and_disabled_tokens_are_refused(lib, monkeypatch):
    s, db = lib
    uid = A.create_user(db, "bot", "agent")
    live = A.create_token(db, uid, "live")
    short = A.create_token(db, uid, "short", ttl_s=60)
    revoked = A.create_token(db, uid, "revoked")
    A.revoke(db, db.q1("SELECT id FROM tokens WHERE name='revoked'")["id"])
    assert A.authenticate_token(db, live) and A.authenticate_token(db, short)
    assert A.authenticate_token(db, revoked) is None
    assert A.authenticate_token(db, "mc_nope_nope") is None and A.authenticate_token(db, "not-a-token") is None
    real_now = A.now
    monkeypatch.setattr(A, "now", lambda: real_now() + 120)
    assert A.authenticate_token(db, short) is None and A.authenticate_token(db, live)
    with _app(s, db) as c:
        r = c.get("/api/library/stats", headers={"Authorization": f"Bearer {short}"})
        assert r.status_code == 401 and r.json()["detail"] == "invalid or expired token"
        assert c.get("/api/library/stats", headers={"Authorization": f"Bearer {revoked}"}).status_code == 401
        assert c.get("/api/library/stats", headers={"Authorization": f"Bearer {live}"}).status_code == 200
    db.x("UPDATE users SET disabled=1 WHERE id=?", (uid,))
    assert A.authenticate_token(db, live) is None


def test_token_scopes_never_widen_past_the_role(lib):
    s, db = lib
    bot = A.create_user(db, "bot", "agent")
    assert A.authenticate_token(db, A.create_token(db, bot, "default")).scopes == A.AGENT_DEFAULT
    for scope in ("rights:write", "admin", "ingest:write"):
        with pytest.raises(ValueError):
            A.create_token(db, bot, "wide", [scope])
    ed = A.create_user(db, "ed", "editor", PW)
    tok = A.create_token(db, ed, "full")
    assert "media:export" in A.authenticate_token(db, tok).scopes
    # Demoting the user narrows the tokens they already hold.
    db.x("UPDATE users SET role='viewer' WHERE id=?", (ed,))
    assert A.authenticate_token(db, tok).scopes == {"library:read"}
    # A narrowed token stays narrow.
    narrow = A.create_token(db, A.create_user(db, "ad", "admin", PW), "ro", ["library:read"])
    assert A.authenticate_token(db, narrow).scopes == {"library:read"}


def test_agents_cannot_log_in_with_a_password(lib):
    s, db = lib
    A.create_user(db, "bot", "agent", PW)
    A.create_user(db, "vera", "viewer", PW)
    assert A.login(db, "bot", PW) is None
    assert A.login(db, "vera", "wrong password") is None and A.login(db, "nobody", PW) is None
    assert A.login(db, "vera", PW).startswith("mc_")
