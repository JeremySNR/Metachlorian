"""Import queue for web links: one row per video (playlists expand into rows), run by a small thread pool
in the server process. Finished files land in ``<library>/imports/<folder>/`` and are analysed like any
other file. Each imported file remembers where it came from (link, title, channel, upload date, licence),
which becomes searchable text and pre-fills its rights as *unknown* for a person to check: a video being
online, or labelled Creative Commons by its uploader, is not clearance.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import Settings, classify_endpoint
from ..db import Database, dumps, loads, now
from . import ytdlp

log = logging.getLogger(__name__)
ACTIVE = ("queued", "probing", "downloading")
MAX_PLAYLIST = 500
SITE_FOLDERS = {"youtube": "YouTube", "vimeo": "Vimeo", "archiveorg": "Internet Archive", "generic": "Web", "dailymotion": "Dailymotion",
                "twitch": "Twitch", "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook", "twitter": "X"}


def imports_root(settings: Settings) -> Path:
    return settings.data_dir / "imports"


def safe_folder(name: str) -> str:
    """A relative folder under imports/: no absolute paths, no '..', no odd characters."""
    parts = [re.sub(r"[^\w .,()&'+-]", "", p).strip(" .") for p in re.split(r"[\\/]+", name or "")]
    return "/".join(p for p in parts if p and p not in (".", ".."))[:200]


def check_url(url: str, settings: Settings) -> str:
    url = (url or "").strip()
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError(f"not a web link: {url[:200]!r} (use an http:// or https:// address)")
    if settings.require_auth:
        # Team mode: don't let the server be used to fetch addresses on its own network.
        try:
            ip = ipaddress.ip_address(u.hostname)
            private = ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            private = classify_endpoint(url)[0]  # names on the local network, or resolving only to private addresses
        if private:
            raise ValueError("links to addresses on the server's own network are not allowed in team mode")
    return url


def enqueue(db: Database, settings: Settings, urls: list[str], folder: str = "", playlist: bool = False,
            max_height: int | None = None, actor: str = "") -> list[int]:
    clean = [check_url(u, settings) for u in urls if (u or "").strip()]
    if not clean:
        raise ValueError("give at least one link")
    if len(clean) > 200:
        raise ValueError("at most 200 links at a time")
    h = int(max_height or settings.import_max_height or 1080)
    if h not in (360, 480, 720, 1080, 1440, 2160, 4320):
        raise ValueError("max_height must be one of 360, 480, 720, 1080, 1440, 2160, 4320")
    ts = now()
    ids = []
    with db.tx() as c:
        for u in dict.fromkeys(clean):
            cur = c.execute("INSERT INTO imports(url, folder, playlist, max_height, actor, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                            (u, safe_folder(folder), int(bool(playlist)), h, actor, ts, ts))
            ids.append(cur.lastrowid)
    runner(settings).kick()
    return ids


def row(db: Database, import_id: int) -> dict[str, Any] | None:
    r = db.q1("SELECT i.*, a.uid asset_uid FROM imports i LEFT JOIN assets a ON a.id=i.asset_id WHERE i.id=?", (import_id,))
    return _public(r) if r else None


def _public(r) -> dict[str, Any]:
    d = dict(r)
    d["info"] = loads(d.get("info"), {}) or {}
    d.pop("asset_id", None)
    d["playlist"] = bool(d["playlist"])
    return d


def listing(db: Database, status: str | None = None, limit: int = 200) -> dict[str, Any]:
    where = "WHERE i.status=?" if status else ""
    rows = db.q(f"SELECT i.*, a.uid asset_uid FROM imports i LEFT JOIN assets a ON a.id=i.asset_id {where}"
                " ORDER BY (i.status IN ('queued','probing','downloading')) DESC, i.id DESC LIMIT ?", (*([status] if status else []), limit))
    counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM imports GROUP BY status")}
    return {"imports": [_public(r) for r in rows], "counts": counts}


def cancel(db: Database, settings: Settings, import_id: int) -> None:
    r = db.q1("SELECT status FROM imports WHERE id=?", (import_id,))
    if not r:
        raise KeyError(import_id)
    if r["status"] in ACTIVE:
        db.x("UPDATE imports SET status='cancelled', message='Cancelled', updated_at=? WHERE id=?", (now(), import_id))
        runner(settings).cancel(import_id)


def retry(db: Database, settings: Settings, import_id: int) -> None:
    r = db.q1("SELECT status FROM imports WHERE id=?", (import_id,))
    if not r:
        raise KeyError(import_id)
    if r["status"] in ("failed", "cancelled"):
        db.x("UPDATE imports SET status='queued', progress=0, error=NULL, message='', updated_at=? WHERE id=?", (now(), import_id))
        runner(settings).kick()


def forget(db: Database, import_id: int) -> None:
    """Remove a finished, failed or cancelled row from the list (the imported file stays in the library)."""
    r = db.q1("SELECT status FROM imports WHERE id=?", (import_id,))
    if not r:
        raise KeyError(import_id)
    if r["status"] in ACTIVE:
        raise ValueError("cancel the import first")
    db.x("DELETE FROM imports WHERE id=?", (import_id,))


def origin_for_asset(db: Database, asset_id: int) -> dict[str, Any] | None:
    r = db.q1("SELECT url, title, site, uploader, info, created_at FROM imports WHERE asset_id=? AND status IN ('done','duplicate')"
              " ORDER BY id LIMIT 1", (asset_id,))
    if not r:
        return None
    info = loads(r["info"], {}) or {}
    return {"url": info.get("webpage_url") or r["url"], "title": r["title"], "site": r["site"], "uploader": r["uploader"],
            "upload_date": _iso(info.get("upload_date")), "license": info.get("license"), "tags": (info.get("tags") or [])[:20],
            "description": (info.get("description") or "")[:2000], "imported_at": r["created_at"]}


def _iso(d: Any) -> str | None:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if isinstance(d, str) and re.fullmatch(r"\d{8}", d) else None


class _Runner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.Lock()
        self.active: dict[int, ytdlp.Runner] = {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="import")
        self.wake = threading.Event()
        self.thread: threading.Thread | None = None
        db = Database(settings.db_path)
        # Anything left mid-way by a previous server run starts again.
        db.x("UPDATE imports SET status='queued', progress=0, message='Restarted', updated_at=? WHERE status IN ('probing','downloading')", (now(),))

    def kick(self) -> None:
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._loop, daemon=True, name="imports")
                self.thread.start()
        self.wake.set()

    def cancel(self, import_id: int) -> None:
        r = self.active.get(import_id)
        if r:
            r.cancel()

    def _loop(self) -> None:
        db = Database(self.settings.db_path)
        while True:
            self.wake.clear()
            with self.lock:
                free = 2 - len(self.active)
            if free > 0:
                taken = []
                with db.tx() as c:
                    for r in c.execute("SELECT id FROM imports WHERE status='queued' ORDER BY id LIMIT ?", (free,)).fetchall():
                        c.execute("UPDATE imports SET status='probing', message='Checking the link…', updated_at=? WHERE id=?", (now(), r["id"]))
                        taken.append(r["id"])
                for iid in taken:
                    with self.lock:
                        self.active[iid] = ytdlp.Runner("")
                    self.pool.submit(self._run, iid)
            if not self.wake.wait(2.0) and not self.active and not db.q1("SELECT 1 FROM imports WHERE status='queued' LIMIT 1"):
                return

    def _run(self, iid: int) -> None:
        db = Database(self.settings.db_path)
        try:
            _process(db, self.settings, iid, self)
        except Exception as e:  # noqa: BLE001 - every failure becomes a readable row
            msg = str(e) if isinstance(e, (ytdlp.YtDlpError, ValueError)) else f"{type(e).__name__}: {e}"
            if msg != "cancelled":
                hint = ytdlp.login_hint(msg, self.settings) if isinstance(e, ytdlp.YtDlpError) else ""
                db.x("UPDATE imports SET status='failed', error=?, message='Failed', updated_at=? WHERE id=? AND status<>'cancelled'",
                     ((msg + (" " + hint if hint else ""))[:2000], now(), iid))
            log.info("import %s failed: %s", iid, msg)
        finally:
            with self.lock:
                self.active.pop(iid, None)
            self.wake.set()


_runners: dict[str, _Runner] = {}
_runners_lock = threading.Lock()


def runner(settings: Settings) -> _Runner:
    key = str(settings.data_dir.resolve())
    with _runners_lock:
        if key not in _runners:
            _runners[key] = _Runner(settings)
        return _runners[key]


def _process(db: Database, settings: Settings, iid: int, owner: _Runner) -> None:
    job = db.q1("SELECT * FROM imports WHERE id=?", (iid,))
    if not job or job["status"] == "cancelled":
        return
    last = [0.0]

    def progress(frac: float, msg: str) -> None:
        t = time.time()
        if t - last[0] < 0.7 and 0 <= frac < 0.99:
            return
        last[0] = t
        db.x("UPDATE imports SET progress=?, message=?, updated_at=? WHERE id=? AND status<>'cancelled'",
             (max(0.0, frac) if frac >= 0 else -1, msg, now(), iid))

    exe = ytdlp.ensure(settings, progress)
    r = ytdlp.Runner(exe)
    owner.active[iid] = r
    entries = r.with_self_update(lambda: ytdlp.probe(r, settings, job["url"], bool(job["playlist"])), progress)
    if _cancelled(db, iid):
        return
    if job["playlist"] and (len(entries) != 1 or entries[0].get("playlist_title")):
        # A playlist or channel: one import per video, in the playlist's folder.
        if not entries:
            raise ytdlp.YtDlpError("The playlist has no videos that can be downloaded.")
        folder = job["folder"] or safe_folder(f"{_site_folder(entries[0].get('site'))}/{entries[0].get('playlist_title') or 'Playlist'}")
        ts = now()
        with db.tx() as c:
            for e in entries[:MAX_PLAYLIST]:
                c.execute("INSERT INTO imports(url, parent_id, folder, playlist, max_height, title, site, duration, actor, created_at, updated_at)"
                          " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (e["url"], iid, folder, 0, job["max_height"], e.get("title"), e.get("site"), e.get("duration"), job["actor"], ts, ts))
            more = f" (first {MAX_PLAYLIST} of {len(entries)})" if len(entries) > MAX_PLAYLIST else ""
            c.execute("UPDATE imports SET status='expanded', progress=1, title=?, message=?, folder=?, updated_at=? WHERE id=?",
                      (entries[0].get("playlist_title") or job["url"], f"{min(len(entries), MAX_PLAYLIST)} videos queued{more}", folder, ts, iid))
        owner.kick()
        return
    e = entries[0]
    key = f"{(e.get('site') or 'web').lower()}:{e.get('id') or e['url']}"
    info = e.get("info") or {}
    db.x("UPDATE imports SET origin_key=?, title=?, site=?, uploader=?, duration=?, info=?, updated_at=? WHERE id=?",
         (key, e.get("title"), e.get("site"), info.get("uploader") or info.get("channel"), e.get("duration"), dumps(info), now(), iid))
    prev = db.q1("SELECT asset_id FROM imports i JOIN assets a ON a.id=i.asset_id WHERE i.origin_key=? AND i.status='done'"
                 " AND a.deleted_at IS NULL AND i.id<>? LIMIT 1", (key, iid))
    if prev:
        db.x("UPDATE imports SET status='duplicate', progress=1, asset_id=?, message='Already in the library', updated_at=? WHERE id=?",
             (prev["asset_id"], now(), iid))
        return
    db.x("UPDATE imports SET status='downloading', message='Downloading video…', updated_at=? WHERE id=? AND status<>'cancelled'", (now(), iid))
    incoming = settings.data_dir / "cache" / "import-incoming" / str(iid)  # outside the library folder until complete
    try:
        path, full = r.with_self_update(lambda: ytdlp.download(r, settings, e["url"], incoming, job["max_height"], progress), progress)
        if _cancelled(db, iid):
            return
        info = {**info, **full}
        folder = job["folder"] or _site_folder(e.get("site"))
        dest_dir = imports_root(settings) / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        k = 1
        while dest.exists():
            dest = dest_dir / f"{path.stem}-{k}{path.suffix}"
            k += 1
        shutil.move(str(path), dest)
    finally:
        shutil.rmtree(incoming, ignore_errors=True)
    up = _iso(info.get("upload_date"))
    if up:
        # The file's date is the upload date, so folder date ranges and date filters mean something.
        t = dt.datetime.fromisoformat(up).replace(tzinfo=dt.timezone.utc).timestamp()
        os.utime(dest, (t, t))
    progress(0.98, "Adding to the library…")
    aid = _register(db, settings, dest)
    db.x("UPDATE imports SET status='done', progress=1, message='Imported', path=?, asset_id=?, info=?, title=?, uploader=?, updated_at=?"
         " WHERE id=?", (str(dest), aid, dumps(info), info.get("title") or e.get("title"), info.get("uploader") or info.get("channel"),
                         now(), iid))
    if aid:
        _prefill_rights(db, aid, info, e, job["actor"])
        from ..indexer import index_asset

        try:
            index_asset(db, settings, aid)
        except Exception:  # pragma: no cover - indexing catches up when analysis finishes
            log.exception("indexing imported asset %s", aid)


def _cancelled(db: Database, iid: int) -> bool:
    r = db.q1("SELECT status FROM imports WHERE id=?", (iid,))
    return not r or r["status"] == "cancelled"


def _site_folder(site: str | None) -> str:
    s = site or "Web"
    return SITE_FOLDERS.get(s.lower(), s)


def _register(db: Database, settings: Settings, path: Path) -> int | None:
    from ..pipeline import plan_asset
    from .scan import add_source, register_file

    root = imports_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    src = db.q1("SELECT id FROM sources WHERE uri=?", (str(root.resolve()),))
    sid = src["id"] if src else add_source(db, str(root), watch=False, priority=5)
    _, aid = register_file(db, path, sid, 5)
    if aid:
        plan_asset(db, settings, aid)
    return aid


def _prefill_rights(db: Database, aid: int, info: dict[str, Any], e: dict[str, Any], actor: str) -> None:
    from .. import rights as R

    if db.q1("SELECT 1 FROM rights WHERE asset_id=? AND shot_id IS NULL", (aid,)):
        return  # a person already recorded rights for this file (e.g. the same video imported before)
    lic = (info.get("license") or "").strip()
    who = info.get("uploader") or info.get("channel") or ""
    url = info.get("webpage_url") or e["url"]
    notes = f"Downloaded from {url}"
    if lic:
        notes += f". The site lists the licence as: {lic}"
    notes += ". Check the rights and mark it cleared before using it; agents only see cleared footage."
    data = {"source": f"{_site_folder(e.get('site'))}: {url}"[:300], "owner": who[:200], "status": "unknown", "notes": notes[:2000]}
    if re.search(r"creative commons", lic, re.I):
        data["licence"] = "CC BY (as stated by the uploader)" if re.search(r"attribution", lic, re.I) else "Creative Commons (as stated by the uploader)"
        data["attribution"] = f"{who} ({_site_folder(e.get('site'))})"[:200] if who else ""
    try:
        R.set_rights(db, aid, data, actor or "import")
    except ValueError:
        log.exception("could not pre-fill rights for imported asset %s", aid)
