"""Discover video files in watch folders and object storage, hash them and
register them as assets. Unchanged files are skipped; moved or duplicated
files are recognised by content hash and never re-processed."""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from ..db import Database, dumps, now

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mxf", ".mts", ".m2ts", ".ts", ".mpg", ".mpeg",
              ".wmv", ".flv", ".3gp", ".dv", ".braw", ".r3d", ".insv", ".lrv"}
# Formats ffmpeg cannot decode without vendor SDKs: registered but flagged.
NEEDS_VENDOR_SDK = {".braw", ".r3d"}
# Camera sidecar/low-res proxies that duplicate a master file.
SKIP_SUFFIXES = {".lrv", ".thm"}

CHUNK = 1 << 20


def new_uid(prefix: str = "a") -> str:
    """Sortable, URL-safe id: time-based prefix + randomness."""
    t = int(time.time() * 1000)
    return f"{prefix}{t:011x}{secrets.token_hex(4)}"


def quick_hash(path: str | Path, size: int | None = None) -> str:
    """Cheap fingerprint: size + 3 x 1 MiB samples. Detects changes without reading whole files."""
    p = Path(path)
    size = p.stat().st_size if size is None else size
    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode())
    with p.open("rb") as f:
        for off in (0, max(0, size // 2 - CHUNK // 2), max(0, size - CHUNK)):
            f.seek(off)
            h.update(f.read(CHUNK))
    return h.hexdigest()


def content_hash(path: str | Path) -> str:
    """Full BLAKE2b of the file, used to recognise duplicates across paths."""
    h = hashlib.blake2b(digest_size=20)
    with Path(path).open("rb") as f:
        while chunk := f.read(8 * CHUNK):
            h.update(chunk)
    return h.hexdigest()


def iter_videos(root: str | Path) -> Iterator[Path]:
    root = Path(root)
    if root.is_file():
        if root.suffix.lower() in VIDEO_EXTS:
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("@eaDir", "#recycle", "$RECYCLE.BIN")]
        for fn in filenames:
            if fn.startswith("._") or fn.startswith("."):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in VIDEO_EXTS and ext not in SKIP_SUFFIXES:
                yield Path(dirpath) / fn


@dataclass
class ScanResult:
    added: int = 0
    changed: int = 0
    unchanged: int = 0
    duplicates: int = 0
    missing: int = 0
    asset_ids: list[int] | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "asset_ids"} | {"asset_ids": self.asset_ids or []}


def register_file(db: Database, path: str | Path, source_id: int | None = None, priority: int = 0,
                  local_path: Path | None = None) -> tuple[str, int | None]:
    """Register one file. Returns (outcome, asset_id) where outcome is
    added | changed | unchanged | duplicate. ``path`` is the canonical
    location (a local path or an s3:// uri); ``local_path`` the readable copy."""
    key = str(path)
    lp = Path(local_path or path)
    name = key.rstrip("/").rsplit("/", 1)[-1]
    suffix = os.path.splitext(name)[1].lower()
    st = lp.stat()
    row = db.q1("SELECT a.id, a.size, a.mtime, a.quick_hash, a.deleted_at FROM asset_paths p JOIN assets a ON a.id=p.asset_id WHERE p.path=?", (key,))
    if row and row["size"] == st.st_size and abs(row["mtime"] - st.st_mtime) < 1e-3 and row["deleted_at"] is None:
        db.x("UPDATE asset_paths SET seen_at=? WHERE path=?", (now(), key))
        return "unchanged", row["id"]
    qh = quick_hash(lp, st.st_size)
    if row and row["quick_hash"] == qh and row["deleted_at"] is None:
        with db.tx() as c:
            c.execute("UPDATE asset_paths SET seen_at=?, mtime=? WHERE path=?", (now(), st.st_mtime, key))
            c.execute("UPDATE assets SET mtime=? WHERE id=?", (st.st_mtime, row["id"]))
        return "unchanged", row["id"]
    ch = content_hash(lp)
    dup = db.q1("SELECT id, path FROM assets WHERE content_hash=? AND deleted_at IS NULL", (ch,))
    with db.tx() as c:
        if dup and (row is None or row["id"] != dup["id"]):
            # Same bytes already known under another path: record the extra location only.
            if row:
                c.execute("DELETE FROM asset_paths WHERE path=?", (key,))
            c.execute("INSERT OR REPLACE INTO asset_paths(asset_id, path, mtime, size, seen_at) VALUES(?,?,?,?,?)",
                      (dup["id"], key, st.st_mtime, st.st_size, now()))
            if not Path(dup["path"]).exists() and not str(dup["path"]).startswith("s3://"):
                c.execute("UPDATE assets SET path=?, filename=?, status=CASE WHEN status='missing' THEN 'ready' ELSE status END WHERE id=?",
                          (key, name, dup["id"]))
            return "duplicate", dup["id"]
        if row:
            # File at a known path changed content: keep identity, reset processing.
            c.execute("UPDATE assets SET size=?, mtime=?, quick_hash=?, content_hash=?, local_path=?, status='new', updated_at=?, deleted_at=NULL WHERE id=?",
                      (st.st_size, st.st_mtime, qh, ch, None if str(lp) == key else str(lp), now(), row["id"]))
            c.execute("UPDATE asset_paths SET mtime=?, size=?, seen_at=? WHERE path=?", (st.st_mtime, st.st_size, now(), key))
            return "changed", row["id"]
        uid = new_uid("a")
        status = "error" if suffix in NEEDS_VENDOR_SDK else "new"
        cur = c.execute(
            "INSERT INTO assets(uid, source_id, path, filename, local_path, size, mtime, quick_hash, content_hash, status, priority, created_at, updated_at, summary)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, source_id, key, name, None if str(lp) == key else str(lp), st.st_size, st.st_mtime, qh, ch, status, priority, now(), now(),
             dumps({"error": "Needs the camera vendor's SDK to decode; transcode to ProRes/H.264 first."} if status == "error" else {})))
        aid = cur.lastrowid
        c.execute("INSERT INTO asset_paths(asset_id, path, mtime, size, seen_at) VALUES(?,?,?,?,?)", (aid, key, st.st_mtime, st.st_size, now()))
        return "added", aid


def add_source(db: Database, uri: str, watch: bool = True, priority: int = 0, options: dict | None = None) -> int:
    kind = "s3" if uri.startswith("s3://") else "folder"
    if kind == "folder":
        uri = str(Path(uri).expanduser().resolve())
    row = db.q1("SELECT id FROM sources WHERE uri=?", (uri,))
    if row:
        return row["id"]
    cur = db.x("INSERT INTO sources(uri, kind, watch, priority, options, created_at) VALUES(?,?,?,?,?,?)",
               (uri, kind, int(watch), priority, dumps(options or {}), now()))
    return cur.lastrowid


def scan_source(db: Database, source_id: int, cache_dir: Path | None = None) -> ScanResult:
    src = db.q1("SELECT * FROM sources WHERE id=?", (source_id,))
    if not src:
        raise KeyError(source_id)
    res = ScanResult(asset_ids=[])
    seen: set[str] = set()
    if src["kind"] == "s3":
        from .s3 import iter_s3_videos

        assert cache_dir is not None
        items: Iterable[tuple[str | Path, Path]] = iter_s3_videos(src["uri"], cache_dir)
    else:
        items = ((p, p) for p in iter_videos(src["uri"]))
    for canonical, local in items:
        try:
            outcome, aid = register_file(db, str(canonical), source_id, src["priority"], local_path=Path(local))
        except (OSError, PermissionError) as e:
            log.warning("cannot read %s: %s", canonical, e)
            continue
        seen.add(str(canonical))
        setattr(res, outcome if outcome != "duplicate" else "duplicates", getattr(res, outcome if outcome != "duplicate" else "duplicates") + 1)
        if outcome in ("added", "changed") and aid:
            res.asset_ids.append(aid)
    # Files that disappeared from this source.
    if src["kind"] == "folder":
        for r in db.q("SELECT p.path, p.asset_id FROM asset_paths p JOIN assets a ON a.id=p.asset_id WHERE a.source_id=? AND a.deleted_at IS NULL", (source_id,)):
            if r["path"] not in seen and not Path(r["path"]).exists():
                with db.tx() as c:
                    c.execute("DELETE FROM asset_paths WHERE path=?", (r["path"],))
                    left = c.execute("SELECT path FROM asset_paths WHERE asset_id=? LIMIT 1", (r["asset_id"],)).fetchone()
                    if left:
                        c.execute("UPDATE assets SET path=? WHERE id=?", (left["path"], r["asset_id"]))
                    else:
                        c.execute("UPDATE assets SET status='missing', updated_at=? WHERE id=?", (now(), r["asset_id"]))
                        res.missing += 1
    db.x("UPDATE sources SET last_scan=? WHERE id=?", (now(), source_id))
    return res
