"""Authentication, roles, scopes and the audit log.

Roles: viewer, editor, admin, agent. Each role has default scopes; tokens can
narrow them (never widen beyond the role). Agents get read-only access unless
a token explicitly grants more, can never change rights or administer, and
every agent call is written to the audit log.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any

from ..db import Database, dumps, loads, now

SCOPES = {
    "library:read": "Search and read shots, assets, collections and rights",
    "media:export": "Export clips and build packages",
    "collections:write": "Create and edit collections",
    "tags:write": "Correct tags and descriptions",
    "rights:write": "Edit rights, releases and expiry",
    "ingest:write": "Add sources, upload files, re-process",
    "admin": "Users, tokens, settings and the audit log",
}
ROLE_SCOPES = {
    "viewer": {"library:read"},
    "editor": {"library:read", "media:export", "collections:write", "tags:write", "ingest:write"},
    "admin": set(SCOPES),
    # Agents: read by default; tokens may add export/collections/tags. Never rights or admin.
    "agent": {"library:read", "media:export", "collections:write", "tags:write"},
}
AGENT_DEFAULT = {"library:read"}
ROLES = tuple(ROLE_SCOPES)


@dataclass
class Principal:
    user_id: int | None
    username: str
    role: str
    scopes: set[str] = field(default_factory=set)
    via: str = "api"
    token_id: int | None = None

    def can(self, scope: str) -> bool:
        return scope in self.scopes

    @property
    def is_agent(self) -> bool:
        return self.role == "agent"

    def as_dict(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "username": self.username, "role": self.role, "scopes": sorted(self.scopes), "via": self.via}


LOCAL_ADMIN = Principal(None, "local", "admin", set(SCOPES), "local")


class Forbidden(Exception):
    pass


def hash_password(pw: str) -> str:
    from argon2 import PasswordHasher

    return PasswordHasher().hash(pw)


def verify_password(h: str, pw: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError

    try:
        return PasswordHasher().verify(h, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _thash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(db: Database, username: str, role: str, password: str | None = None, display_name: str = "") -> int:
    if role not in ROLE_SCOPES:
        raise ValueError(f"role must be one of {ROLES}")
    if not username or len(username) > 64:
        raise ValueError("username must be 1-64 characters")
    if password is not None and len(password) < 10:
        raise ValueError("passwords must be at least 10 characters")
    cur = db.x("INSERT INTO users(username, display_name, role, password_hash, created_at) VALUES(?,?,?,?,?)",
               (username, display_name or username, role, hash_password(password) if password else None, now()))
    return cur.lastrowid


def create_token(db: Database, user_id: int, name: str, scopes: list[str] | None = None, kind: str = "api",
                 ttl_s: float | None = None) -> str:
    u = db.q1("SELECT role FROM users WHERE id=?", (user_id,))
    if not u:
        raise KeyError(user_id)
    allowed = ROLE_SCOPES[u["role"]]
    if scopes is None:
        scopes = sorted(AGENT_DEFAULT if u["role"] == "agent" else allowed)
    bad = [s for s in scopes if s not in allowed]
    if bad:
        raise ValueError(f"role {u['role']} cannot hold scopes {bad}")
    secret = secrets.token_urlsafe(32)
    prefix = secrets.token_hex(3)
    token = f"mc_{prefix}_{secret}"
    db.x("INSERT INTO tokens(user_id, name, prefix, token_hash, scopes, kind, created_at, expires_at) VALUES(?,?,?,?,?,?,?,?)",
         (user_id, name, prefix, _thash(token), dumps(sorted(scopes)), kind, now(), now() + ttl_s if ttl_s else None))
    return token


def authenticate_token(db: Database, token: str, via: str = "api") -> Principal | None:
    if not token or not token.startswith("mc_"):
        return None
    r = db.q1("SELECT t.id, t.scopes, t.expires_at, t.revoked, t.last_used, u.id uid, u.username, u.role, u.disabled FROM tokens t"
              " JOIN users u ON u.id=t.user_id WHERE t.token_hash=?", (_thash(token),))
    if not r or r["revoked"] or r["disabled"] or (r["expires_at"] and r["expires_at"] < now()):
        return None
    if not r["last_used"] or now() - r["last_used"] > 60:
        db.x("UPDATE tokens SET last_used=? WHERE id=?", (now(), r["id"]))
    scopes = set(loads(r["scopes"], [])) & ROLE_SCOPES[r["role"]]
    return Principal(r["uid"], r["username"], r["role"], scopes, via, r["id"])


def login(db: Database, username: str, password: str) -> str | None:
    r = db.q1("SELECT id, password_hash, disabled, role FROM users WHERE username=?", (username,))
    if not r or r["disabled"] or not r["password_hash"] or r["role"] == "agent":
        # Constant-ish time: still hash to avoid user enumeration by timing.
        verify_password("$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+dWRWJTmaaJObG", password)
        return None
    if not verify_password(r["password_hash"], password):
        return None
    return create_token(db, r["id"], "session", kind="session", ttl_s=14 * 24 * 3600)


def revoke(db: Database, token_id: int) -> None:
    db.x("UPDATE tokens SET revoked=1 WHERE id=?", (token_id,))


def audit(db: Database, p: Principal, action: str, target: str = "", detail: dict[str, Any] | None = None, ok: bool = True) -> None:
    try:
        db.x("INSERT INTO audit_log(at, user_id, actor, role, via, action, target, detail, ok) VALUES(?,?,?,?,?,?,?,?,?)",
             (now(), p.user_id, p.username, p.role, p.via, action, target, dumps(detail or {})[:8000], int(ok)))
    except Exception:  # pragma: no cover - auditing must not break requests
        pass


def require(p: Principal, scope: str) -> None:
    if not p.can(scope):
        raise Forbidden(f"'{p.username}' ({p.role}) lacks the '{scope}' scope")
