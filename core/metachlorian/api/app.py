"""REST API, media serving, the web app and the MCP endpoint in one ASGI app.

Security model:
* Team mode (require_auth): every request needs a session cookie or a bearer
  token. State-changing requests authenticated by cookie must carry the
  ``X-Metachlorian: 1`` header (a custom header cannot be sent cross-site
  without a CORS preflight, which we never grant), so cookies alone cannot be
  used for CSRF.
* Solo mode (no auth, loopback only): requests from 127.0.0.1 act as the local
  admin, but only when the Host header is a loopback name (defeats DNS
  rebinding) and, for writes, with the custom header.
"""
from __future__ import annotations

import contextlib
import ipaddress
import logging
import mimetypes
import os
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .. import __version__, auth as A, models
from ..auth import LOCAL_ADMIN, Forbidden, Principal
from ..config import Settings
from ..db import Database
from ..search.engine import SearchRequest
from ..service import Library, NotFound

log = logging.getLogger(__name__)
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
APP_DIST_CANDIDATES = [Path(__file__).resolve().parents[3] / "app" / "dist", Path(os.environ.get("METACHLORIAN_APP_DIST", "/nonexistent"))]


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in LOOPBACK_HOSTS


def _host_only(host: str) -> str:
    """The host part of a Host header: 'a:8765' -> 'a', '[::1]:8765' and '[::1]' -> '::1'."""
    host = host.strip()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host[1:]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def create_app(settings: Settings, db: Database | None = None, start_workers: bool = True) -> FastAPI:
    settings.ensure_dirs()
    db = db or Database(settings.db_path)
    lib = Library(db, settings)
    from ..mcp_server.server import build_server

    mcp = build_server(lib)
    mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True)
    background: dict[str, Any] = {}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_workers:
            from ..runtime import start_background

            background.update(start_background(settings))
        # Warm the vector index and text encoder so the first search is fast.
        threading.Thread(target=_warm, args=(lib,), daemon=True).start()
        async with mcp.session_manager.run() if getattr(mcp, "_session_manager", None) is not None or hasattr(mcp, "session_manager") else contextlib.nullcontext():
            yield
        if background.get("stop"):
            background["stop"]()
        lib.engine.vectors.save_all()

    app = FastAPI(title="Metachlorian", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.lib = lib
    app.state.settings = settings

    def _scope(folder: list[str] | None, collection: list[str] | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if folder:
            out["folder"] = folder
        if collection:
            out["collection"] = collection
        return out

    def _intended(use, channel, territory, include) -> dict[str, Any] | None:
        if not (use or channel or territory):
            return None
        d: dict[str, Any] = {"use": use, "channel": channel, "territory": territory}
        if include:
            d["include"] = [x for x in include.split(",") if x]
        return d

    # ------------------------------------------------------------------ auth
    def principal(request: Request) -> Principal:
        p = getattr(request.state, "principal", None)
        if p is None:
            raise HTTPException(401, "authentication required")
        return p

    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            request.state.principal = None
            host = _host_only(request.headers.get("host") or "")
            client = request.client.host if request.client else None
            token = None
            via_cookie = False
            authz = request.headers.get("authorization", "")
            if authz.lower().startswith("bearer "):
                token = authz[7:].strip()
            elif request.cookies.get("mc_session"):
                token = request.cookies.get("mc_session")
                via_cookie = True
            elif request.query_params.get("token") and path.startswith("/media/"):
                token = request.query_params.get("token")
            p = A.authenticate_token(db, token, via="api") if token else None
            if p is None and not settings.require_auth:
                if _is_loopback(client) and (host in LOOPBACK_HOSTS or _is_loopback(host)):
                    p = Principal(None, "local", "admin", set(A.SCOPES), "ui")
                    via_cookie = True  # browser-originated: apply the CSRF header rule
            if token and p is None and not path.startswith(("/api/health", "/api/auth/login")):
                return JSONResponse({"detail": "invalid or expired token"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Bearer realm="metachlorian"'})
            if path.startswith("/mcp") and not authz.lower().startswith("bearer "):
                return JSONResponse({"detail": "MCP needs 'Authorization: Bearer <token>' (create one in Settings → Agents)"},
                                    status_code=401, headers={"WWW-Authenticate": 'Bearer realm="metachlorian"'})
            if p is not None and via_cookie and request.method not in SAFE_METHODS and not path.startswith("/api/auth/login") \
                    and request.headers.get("x-metachlorian") != "1":
                return JSONResponse({"detail": "missing X-Metachlorian header"}, status_code=403)
            request.state.principal = p
            if path.startswith("/mcp"):
                if p is None or not authz:
                    return JSONResponse({"detail": "MCP needs 'Authorization: Bearer <token>' (create one in Settings → Agents)"},
                                        status_code=401, headers={"WWW-Authenticate": 'Bearer realm="metachlorian"'})
            elif (path.startswith("/api/") or path.startswith("/media/")) and p is None and not path.startswith(("/api/health", "/api/auth/login")):
                return JSONResponse({"detail": "authentication required"}, status_code=401)
            return await call_next(request)

    app.add_middleware(AuthMiddleware)

    @app.exception_handler(Forbidden)
    async def _forbidden(request: Request, exc: Forbidden):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(NotFound)
    async def _nf(request: Request, exc: NotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def _bad(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def _key(request: Request, exc: KeyError):
        return JSONResponse({"detail": f"not found: {exc}"}, status_code=404)

    # ------------------------------------------------------------------ session
    @app.get("/api/health")
    def health():
        return lib.health()

    @app.post("/api/auth/login")
    def login(body: dict = Body(...)):
        tok = A.login(db, body.get("username", ""), body.get("password", ""))
        if not tok:
            raise HTTPException(401, "wrong username or password")
        p = A.authenticate_token(db, tok)
        resp = JSONResponse({"user": p.as_dict() if p else None})
        resp.set_cookie("mc_session", tok, httponly=True, samesite="strict", secure=settings.require_auth and settings.host not in LOOPBACK_HOSTS,
                        max_age=14 * 24 * 3600)
        return resp

    @app.post("/api/auth/logout")
    def logout(request: Request):
        tok = request.cookies.get("mc_session")
        if tok:
            p = A.authenticate_token(db, tok)
            if p and p.token_id:
                A.revoke(db, p.token_id)
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("mc_session")
        return resp

    @app.get("/api/me")
    def me(p: Principal = Depends(principal)):
        return {**p.as_dict(), "solo": not settings.require_auth}

    # ------------------------------------------------------------------ search and read
    @app.post("/api/search")
    def search(body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.search(p, SearchRequest.from_dict(body))

    @app.get("/api/search")
    def search_get(q: str = "", limit: int = 40, cursor: str | None = None, p: Principal = Depends(principal)):
        return lib.search(p, SearchRequest(q=q, limit=limit, cursor=cursor))

    @app.get("/api/shots/{uid}")
    def get_shot(uid: str, use: str | None = None, channel: str | None = None, territory: str | None = None, p: Principal = Depends(principal)):
        intended = {"use": use, "channel": channel, "territory": territory} if (use or channel or territory) else None
        return lib.get_shot(p, uid, intended)

    @app.get("/api/shots/{uid}/similar")
    def similar(uid: str, limit: int = 24, modality: str = "visual", use: str | None = None, channel: str | None = None,
                territory: str | None = None, include: str | None = None, hide_blocked: bool = True,
                folder: list[str] | None = Query(None), collection: list[str] | None = Query(None), p: Principal = Depends(principal)):
        return lib.find_similar(p, shot_uid=uid, limit=limit, modality=modality, intended=_intended(use, channel, territory, include),
                                hide_blocked=hide_blocked, filters=_scope(folder, collection))

    @app.post("/api/similar")
    async def similar_upload(file: UploadFile = File(...), limit: int = 24, use: str | None = None, channel: str | None = None,
                             territory: str | None = None, include: str | None = None, hide_blocked: bool = True,
                             folder: list[str] | None = Query(None), collection: list[str] | None = Query(None),
                             p: Principal = Depends(principal)):
        intended = _intended(use, channel, territory, include)
        scope = _scope(folder, collection)
        data = await file.read()
        if len(data) > 300 * 1024 * 1024:
            raise HTTPException(413, "file too large")
        if (file.content_type or "").startswith("video/") or Path(file.filename or "").suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"):
            with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "x.mp4").suffix, delete=False) as tf:
                tf.write(data)
            try:
                return lib.find_similar(p, clip=Path(tf.name), limit=limit, intended=intended, hide_blocked=hide_blocked, filters=scope)
            finally:
                os.unlink(tf.name)
        return lib.find_similar(p, image=data, limit=limit, intended=intended, hide_blocked=hide_blocked, filters=scope)

    # ------------------------------------------------------------------ people (face identity)
    @app.get("/api/people")
    def people_list(q: str = "", named: bool | None = None, limit: int = 200, offset: int = 0, p: Principal = Depends(principal)):
        return lib.people(p, q, named, limit, offset)

    @app.get("/api/people/{identity_id}")
    def people_get(identity_id: int, limit: int = 200, offset: int = 0, p: Principal = Depends(principal)):
        return lib.person(p, identity_id, limit, offset)

    @app.patch("/api/people/{identity_id}")
    def people_rename(identity_id: int, body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.rename_person(p, identity_id, str(body.get("name") or ""))

    @app.post("/api/people/{identity_id}/merge")
    def people_merge(identity_id: int, body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.merge_people(p, identity_id, int(body["into"]))

    @app.delete("/api/people/{identity_id}")
    def people_forget(identity_id: int, p: Principal = Depends(principal)):
        return lib.forget_person(p, identity_id)

    @app.post("/api/faces/{face_id}/assign")
    def faces_assign(face_id: int, body: dict = Body(...), p: Principal = Depends(principal)):
        """{"identity_id": n} moves the face to that person; {"identity_id": null} means "not this person"."""
        tid = body.get("identity_id")
        return lib.move_face(p, face_id, int(tid) if tid is not None else None)

    @app.get("/api/folders")
    def folders(q: str = "", parent: str | None = None, limit: int = 500, p: Principal = Depends(principal)):
        return lib.folders(p, q, parent, limit)

    @app.get("/api/assets")
    def assets(q: str = "", edit_type: str | None = None, status: str | None = None, limit: int = 200, offset: int = 0,
               folder: str | None = None, collection: str | None = None, p: Principal = Depends(principal)):
        return lib.list_assets(p, q, edit_type, status, limit, offset, folder, collection)

    @app.get("/api/assets/{uid}")
    def asset(uid: str, p: Principal = Depends(principal)):
        return lib.get_asset(p, uid)

    @app.post("/api/assets/{uid}/reprocess")
    def reprocess(uid: str, body: dict = Body(default={}), p: Principal = Depends(principal)):
        return lib.reprocess(p, uid, body.get("analysers"), body.get("priority"))

    @app.delete("/api/assets/{uid}")
    def delete_asset(uid: str, p: Principal = Depends(principal)):
        lib.delete_asset(p, uid)
        return {"ok": True}

    @app.get("/api/library/stats")
    def stats(p: Principal = Depends(principal)):
        return lib.library_stats(p)

    @app.get("/api/vocab")
    def vocab(p: Principal = Depends(principal)):
        return lib.vocabularies(p)

    @app.get("/api/vocab/{name}")
    def vocab_one(name: str, p: Principal = Depends(principal)):
        return lib.vocabularies(p, name)

    @app.post("/api/vocab/{name}/terms")
    def vocab_add(name: str, body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.add_term(p, name, body["term"], body["label"], body.get("definition", ""), body.get("synonyms"), body.get("broader"))

    # ------------------------------------------------------------------ corrections
    @app.get("/api/corrections")
    def corrections(asset_uid: str | None = None, p: Principal = Depends(principal)):
        return {"corrections": lib.corrections(p, asset_uid), "correctable": lib.correctable()}

    @app.post("/api/corrections")
    def correct(body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.correct(p, body["field"], body.get("op", "set"), body.get("value"), body.get("shot_uid"), body.get("asset_uid"), body.get("note", ""))

    @app.delete("/api/corrections/{cid}")
    def revert(cid: int, p: Principal = Depends(principal)):
        lib.revert(p, cid)
        return {"ok": True}

    # ------------------------------------------------------------------ rights
    @app.get("/api/rights/{asset_uid}")
    def rights_get(asset_uid: str, shot_uid: str | None = None, p: Principal = Depends(principal)):
        return lib.get_rights(p, asset_uid, shot_uid)

    @app.put("/api/rights/{asset_uid}")
    def rights_put(asset_uid: str, body: dict = Body(...), shot_uid: str | None = None, p: Principal = Depends(principal)):
        return lib.set_rights(p, asset_uid, body, shot_uid)

    @app.post("/api/rights/bulk")
    def rights_bulk(body: dict = Body(...), p: Principal = Depends(principal)):
        return {"updated": lib.bulk_rights(p, body["asset_uids"], body["rights"])}

    @app.post("/api/rights/check")
    def rights_check(body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.check_rights(p, body.get("shot_uids"), body.get("asset_uids"), body.get("use"), body.get("channel"), body.get("territory"), body.get("date"))

    # ------------------------------------------------------------------ collections and exports
    @app.get("/api/collections")
    def collections(p: Principal = Depends(principal)):
        return {"collections": lib.collections(p)}

    @app.post("/api/collections")
    def collection_new(body: dict = Body(...), p: Principal = Depends(principal)):
        c = lib.create_collection(p, body.get("name", "Untitled"), body.get("description", ""), body.get("kind", "collection"), body.get("brief", ""))
        if body.get("shot_uids"):
            c = lib.add_to_collection(p, c["uid"], body["shot_uids"])
        return c

    @app.get("/api/collections/{uid}")
    def collection(uid: str, p: Principal = Depends(principal)):
        return lib.collection(p, uid)

    @app.patch("/api/collections/{uid}")
    def collection_patch(uid: str, body: dict = Body(...), p: Principal = Depends(principal)):
        if "order" in body:
            return lib.reorder(p, uid, body["order"])
        return lib.update_collection(p, uid, **body)

    @app.delete("/api/collections/{uid}")
    def collection_delete(uid: str, p: Principal = Depends(principal)):
        lib.delete_collection(p, uid)
        return {"ok": True}

    @app.post("/api/collections/{uid}/items")
    def collection_add(uid: str, body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.add_to_collection(p, uid, body["shot_uids"], body.get("in"), body.get("out"), body.get("note", ""))

    @app.patch("/api/collections/{uid}/items/{item_id}")
    def collection_item(uid: str, item_id: int, body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.update_item(p, uid, item_id, **body)

    @app.delete("/api/collections/{uid}/items/{item_id}")
    def collection_remove(uid: str, item_id: int, p: Principal = Depends(principal)):
        return lib.remove_item(p, uid, item_id)

    @app.post("/api/collections/{uid}/package")
    def collection_package(uid: str, body: dict = Body(default={}), p: Principal = Depends(principal)):
        res = lib.build_package(p, collection_uid=uid, name=body.get("name", ""), brief=body.get("brief", ""), target=body.get("target"),
                                media_policy=body.get("media_policy", "proxies"), mode=body.get("mode"), zip_it=bool(body.get("zip", True)))
        return {k: v for k, v in res.items() if k != "manifest"} | {"manifest": res["manifest"]}

    @app.post("/api/package")
    def package(body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.build_package(p, items=body.get("items"), name=body.get("name", ""), brief=body.get("brief", ""), target=body.get("target"),
                                 media_policy=body.get("media_policy", "proxies"), mode=body.get("mode"), zip_it=bool(body.get("zip", False)))

    @app.post("/api/export/clip")
    def export(body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.export_clip(p, body["shot_uid"], body.get("in"), body.get("out"), body.get("mode", "proxy"), body.get("intended_use"))

    @app.get("/api/exports/file")
    def export_file(path: str, p: Principal = Depends(principal)):
        A.require(p, "media:export")
        base = settings.export_dir.resolve()
        target = (base / path).resolve()
        if base not in target.parents and target != base:
            raise HTTPException(400, "bad path")
        if target.is_dir():
            z = target.with_suffix(".zip")
            if not z.exists():
                with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in sorted(target.rglob("*")):
                        if f.is_file():
                            zf.write(f, f"{target.name}/{f.relative_to(target).as_posix()}")
            target = z
        if not target.exists():
            raise HTTPException(404, "not found")
        return FileResponse(target, filename=target.name)

    # ------------------------------------------------------------------ ingest and processing
    @app.get("/api/sources")
    def sources(p: Principal = Depends(principal)):
        return {"sources": lib.sources(p)}

    @app.post("/api/sources")
    def source_add(body: dict = Body(...), p: Principal = Depends(principal)):
        return lib.add_source(p, body["uri"], body.get("watch", True), body.get("scan", True))

    @app.delete("/api/sources/{sid}")
    def source_del(sid: int, p: Principal = Depends(principal)):
        lib.remove_source(p, sid)
        return {"ok": True}

    @app.post("/api/sources/{sid}/scan")
    def source_scan(sid: int, p: Principal = Depends(principal)):
        return lib.scan(p, sid)

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...), p: Principal = Depends(principal)):
        return lib.upload(p, file.filename or "upload.mp4", file.file)

    @app.get("/api/processing")
    def processing(p: Principal = Depends(principal)):
        return lib.processing(p)

    @app.post("/api/processing/retry")
    def retry(p: Principal = Depends(principal)):
        return {"enqueued": lib.retry_failed(p)}

    # ------------------------------------------------------------------ admin
    @app.get("/api/admin/users")
    def users(p: Principal = Depends(principal)):
        A.require(p, "admin")
        return {"users": [dict(r) for r in db.q("SELECT id, username, display_name, role, disabled, created_at FROM users ORDER BY id")]}

    @app.post("/api/admin/users")
    def user_new(body: dict = Body(...), p: Principal = Depends(principal)):
        A.require(p, "admin")
        uid = A.create_user(db, body["username"], body["role"], body.get("password"), body.get("display_name", ""))
        A.audit(db, p, "create_user", body["username"], {"role": body["role"]})
        return {"id": uid}

    @app.patch("/api/admin/users/{uid}")
    def user_patch(uid: int, body: dict = Body(...), p: Principal = Depends(principal)):
        A.require(p, "admin")
        if "role" in body:
            if body["role"] not in A.ROLES:
                raise HTTPException(400, "bad role")
            db.x("UPDATE users SET role=? WHERE id=?", (body["role"], uid))
        if "disabled" in body:
            db.x("UPDATE users SET disabled=? WHERE id=?", (int(bool(body["disabled"])), uid))
        if body.get("password"):
            if len(body["password"]) < 10:
                raise HTTPException(400, "passwords must be at least 10 characters")
            db.x("UPDATE users SET password_hash=? WHERE id=?", (A.hash_password(body["password"]), uid))
        A.audit(db, p, "update_user", str(uid), {k: v for k, v in body.items() if k != "password"})
        return {"ok": True}

    @app.get("/api/admin/tokens")
    def tokens(p: Principal = Depends(principal)):
        A.require(p, "admin")
        rows = db.q("SELECT t.id, t.name, t.prefix, t.scopes, t.kind, t.created_at, t.last_used, t.expires_at, t.revoked, u.username, u.role"
                    " FROM tokens t JOIN users u ON u.id=t.user_id WHERE t.kind='api' ORDER BY t.id DESC")
        return {"tokens": [{**dict(r), "scopes": __import__("json").loads(r["scopes"])} for r in rows], "scopes": A.SCOPES,
                "role_scopes": {k: sorted(v) for k, v in A.ROLE_SCOPES.items()}}

    @app.post("/api/admin/tokens")
    def token_new(body: dict = Body(...), p: Principal = Depends(principal)):
        A.require(p, "admin")
        user = db.q1("SELECT id FROM users WHERE username=?", (body["username"],))
        if not user:
            uid = A.create_user(db, body["username"], body.get("role", "agent"))
        else:
            uid = user["id"]
        tok = A.create_token(db, uid, body.get("name", "agent token"), body.get("scopes"), ttl_s=body.get("ttl_days", 0) * 86400 or None)
        A.audit(db, p, "create_token", body["username"], {"scopes": body.get("scopes"), "name": body.get("name")})
        return {"token": tok, "note": "Shown once. Store it in your agent's MCP configuration."}

    @app.delete("/api/admin/tokens/{tid}")
    def token_del(tid: int, p: Principal = Depends(principal)):
        A.require(p, "admin")
        A.revoke(db, tid)
        A.audit(db, p, "revoke_token", str(tid))
        return {"ok": True}

    @app.get("/api/admin/audit")
    def audit_log(limit: int = 200, actor: str | None = None, agents_only: bool = False, p: Principal = Depends(principal)):
        return {"entries": lib.audit_log(p, limit, actor, agents_only)}

    @app.get("/api/admin/settings")
    def settings_get(p: Principal = Depends(principal)):
        A.require(p, "admin")
        from ..llm import health as llm_health

        return {"settings": settings.public_dict(), "egress": settings.egress_summary(), "models": models.status(settings.resolved_models_dir),
                "vlm_health": llm_health(settings.vlm, settings=settings) if settings.vlm.enabled else None,
                "llm_health": llm_health(settings.llm, settings=settings) if settings.llm.enabled else None}

    @app.get("/api/admin/providers")
    def providers(p: Principal = Depends(principal)):
        A.require(p, "admin")
        from .. import apikeys
        from ..config import PROVIDERS, ModelEndpoint
        from ..llm import codex_remaining, codex_status

        out = []
        keys = apikeys.status(settings)
        for pid, pr in PROVIDERS.items():
            item = {"id": pid, "label": pr["label"], "hosted": pr["hosted"], "base_url": pr["base_url"], "default_models": {
                "vlm": pr["vlm_model"], "llm": pr["llm_model"]}, "concurrency": pr["concurrency"], "batch": pr["batch"]}
            if pr.get("key"):
                item["key"] = {"name": pr["key"], **keys[pr["key"]]}
            if pid == "codex":
                active = settings.vlm if settings.vlm.provider == "codex" else settings.llm if settings.llm.provider == "codex" else None
                ep = active or ModelEndpoint(provider="codex", model=pr["vlm_model"], codex_path=settings.vlm.codex_path or "codex")
                item["status"] = codex_status(ep)
                item["daily_limit"] = ep.effective_daily_limit
                item["remaining_today"] = codex_remaining(settings, ep)
                item["active"] = active is not None
            out.append(item)
        return {"providers": out, "active": {"vlm": settings.vlm.provider, "llm": settings.llm.provider},
                "allow_remote": settings.allow_remote, "egress": settings.egress_summary()}

    @app.put("/api/admin/keys/{name}")
    def put_key(name: str, body: dict = Body(...), p: Principal = Depends(principal)):
        """Store (or clear, with an empty value) a provider API key. The key is never returned."""
        A.require(p, "admin")
        from .. import apikeys

        apikeys.put(settings, name, str(body.get("value") or ""))
        A.audit(db, p, "set_api_key", name, {"cleared": not body.get("value")})
        return apikeys.status(settings)[name]

    @app.post("/api/admin/providers/test")
    def test_provider(body: dict = Body(...), p: Principal = Depends(principal)):
        """Check a provider without spending a model request: key check, model list or Codex login."""
        A.require(p, "admin")
        from ..config import PROVIDERS, ModelEndpoint
        from ..llm import health

        pid = body.get("provider", "custom")
        if pid not in PROVIDERS:
            raise HTTPException(400, f"unknown provider '{pid}'")
        ep = ModelEndpoint(provider=pid, base_url=body.get("base_url", ""), model=body.get("model") or PROVIDERS[pid]["vlm_model"] or "x",
                           codex_path=body.get("codex_path") or "codex")
        return health(ep, timeout=12.0, settings=settings)

    @app.get("/api/admin/providers/openrouter/models")
    def openrouter_catalogue(vision: bool = False, p: Principal = Depends(principal)):
        A.require(p, "admin")
        from ..llm import openrouter_models

        try:
            models_ = openrouter_models()
        except Exception as e:  # network or upstream error: the UI falls back to the suggested defaults
            raise HTTPException(502, f"could not load the OpenRouter catalogue: {e}") from e
        return {"models": [m for m in models_ if m["vision"] or not vision]}

    @app.get("/api/admin/endpoint-locality")
    def endpoint_locality(url: str, p: Principal = Depends(principal)):
        A.require(p, "admin")
        from ..config import classify_endpoint

        local, reason = classify_endpoint(url)
        return {"url": url, "local": local, "reason": reason}

    @app.put("/api/admin/settings")
    def settings_put(body: dict = Body(...), p: Principal = Depends(principal)):
        A.require(p, "admin")
        from ..runtime import save_settings

        save_settings(settings, body)
        A.audit(db, p, "update_settings", "", {k: v for k, v in body.items() if "key" not in k})
        # Newly enabled or changed analysers (e.g. a model provider) are queued now, not at the next periodic re-plan.
        from ..pipeline import plan_all

        threading.Thread(target=lambda: plan_all(Database(settings.db_path), settings), daemon=True).start()
        return {"settings": settings.public_dict(), "egress": settings.egress_summary()}

    # ------------------------------------------------------------------ media
    @app.get("/media/{asset_uid}/{path:path}")
    def media(asset_uid: str, path: str, request: Request, p: Principal = Depends(principal)):
        lib.media_access(p, asset_uid)  # library:read; agents never get media of a file holding blocked shots
        if not asset_uid.replace("-", "").isalnum():
            raise HTTPException(400, "bad asset id")
        base = (settings.media_dir / asset_uid).resolve()
        target = (base / path).resolve()
        if base not in target.parents or not target.is_file():
            raise HTTPException(404, "not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        immutable = target.suffix in (".jpg", ".png") and "sprite" not in target.name
        return FileResponse(target, media_type=ctype, headers={"Cache-Control": "private, max-age=86400" if immutable else "private, max-age=60",
                                                                "Accept-Ranges": "bytes"})

    app.mount("/mcp", mcp_app)

    # ------------------------------------------------------------------ web app
    # Looked up per request, so a freshly built app/dist is served without a restart.
    def _dist() -> Path | None:
        return next((d for d in APP_DIST_CANDIDATES if (d / "index.html").exists()), None)

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        dist = _dist()
        if dist is None:
            return Response("Metachlorian core is running. The web app is not built (run `npm run build` in app/). API docs: /api/docs",
                            media_type="text/plain")
        f = (dist / full_path).resolve()
        if full_path and dist.resolve() in f.parents and f.is_file():
            cache = "public, max-age=31536000, immutable" if "/assets/" in f.as_posix() else "no-cache"
            return FileResponse(f, headers={"Cache-Control": cache})
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    _ = (Query, shutil)
    return app


def _warm(lib: Library) -> None:
    try:
        lib.engine.vectors.get("visual")
        if models.installed(lib.settings.resolved_models_dir, "siglip-base-multilingual"):
            lib.engine._text_vector("warm up")
    except Exception:  # pragma: no cover
        log.exception("warm-up failed")
