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
from typing import Callable, Iterable, Iterator

from filelock import FileLock, Timeout

from ..db import Database, dumps, loads, now

log = logging.getLogger(__name__)

# Everything FFmpeg decodes is analysed: any codec, bit depth (8-16 bit, float), chroma and colour space.
VIDEO_EXTS = {".mp4", ".mov", ".qt", ".m4v", ".mkv", ".webm", ".avi", ".mxf", ".gxf", ".lxf", ".mts", ".m2ts", ".m2t", ".ts",
              ".mpg", ".mpeg", ".m2v", ".mpv", ".vob", ".mod", ".tod", ".wmv", ".asf", ".flv", ".f4v", ".3gp", ".3g2", ".dv",
              ".divx", ".ogv", ".nut", ".y4m", ".ivf", ".rm", ".rmvb", ".cine", ".h264", ".264", ".h265", ".265", ".hevc",
              ".insv", ".360", ".lrv", ".wtv"}
# Camera raw that only the maker's decoder can read. Registered and analysed through a configured raw
# decoder (Settings > Formats) that converts it to a working master; without one, reported clearly.
RAW_EXTS = {".braw": "Blackmagic RAW", ".r3d": "RED R3D", ".ari": "ARRIRAW", ".arx": "ARRIRAW HDE", ".crm": "Canon Cinema RAW Light",
            ".nev": "Nikon N-RAW", ".mcraw": "MotionCam RAW"}
VIDEO_EXTS |= set(RAW_EXTS)
NEEDS_VENDOR_SDK = set(RAW_EXTS)  # kept for callers; raw files are no longer rejected at registration
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


def content_hash(path: str | Path, progress: Callable[[int], None] | None = None) -> str:
    """Full BLAKE2b of the file, used to recognise duplicates across paths."""
    h = hashlib.blake2b(digest_size=20)
    read = 0
    with Path(path).open("rb") as f:
        while chunk := f.read(8 * CHUNK):
            h.update(chunk)
            read += len(chunk)
            if progress:
                progress(read)
    return h.hexdigest()


def path_within(path: str | Path, folder: str | Path) -> bool:
    """Match a complete directory boundary, including Windows case/separator aliases."""
    def normal(value):
        return os.path.normcase(os.path.abspath(str(value))).replace("\\", "/").rstrip("/")
    candidate, parent = normal(path), normal(folder)
    return candidate == parent or candidate.startswith(parent + "/")


def excluded_folders(db: Database) -> list[str]:
    return loads(db.get_meta("ingest:excluded_folders"), [])


def is_excluded(db: Database, path: str | Path) -> bool:
    return any(path_within(path, folder) for folder in excluded_folders(db))


def iter_videos(root: str | Path, on_directory=None, on_error=None, excluded=()) -> Iterator[Path]:
    root = Path(root)
    def skip(path):
        return any(path_within(path, folder) for folder in excluded)
    if skip(root):
        return
    if root.is_file():
        if root.suffix.lower() in VIDEO_EXTS:
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        if on_directory:
            on_directory(dirpath)
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("@eaDir", "#recycle", "$RECYCLE.BIN")
                      and not skip(Path(dirpath) / d)]
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
    excluded: int = 0
    asset_ids: list[int] | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "asset_ids"} | {"asset_ids": self.asset_ids or []}


def register_file(db: Database, path: str | Path, source_id: int | None = None, priority: int = 0,
                  local_path: Path | None = None, on_hash=None) -> tuple[str, int | None]:
    """Register one file. Returns (outcome, asset_id) where outcome is
    added | changed | unchanged | duplicate. ``path`` is the canonical
    location (a local path or an s3:// uri); ``local_path`` the readable copy."""
    key = str(path)
    if is_excluded(db, key):
        return "excluded", None
    lp = Path(local_path or path)
    name = key.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    suffix = os.path.splitext(name)[1].lower()
    st = lp.stat()
    row = db.q1("SELECT a.id, a.size, a.mtime, a.quick_hash, a.deleted_at FROM asset_paths p JOIN assets a ON a.id=p.asset_id WHERE p.path=?", (key,))
    if row and source_id is not None:
        db.x("UPDATE assets SET source_id=COALESCE(source_id,?) WHERE id=?", (source_id, row["id"]))
    if row and row["size"] == st.st_size and abs(row["mtime"] - st.st_mtime) < 1e-3 and row["deleted_at"] is None:
        db.x("UPDATE asset_paths SET seen_at=? WHERE path=?", (now(), key))
        return "unchanged", row["id"]
    qh = quick_hash(lp, st.st_size)
    if row and row["quick_hash"] == qh and row["deleted_at"] is None:
        with db.tx() as c:
            c.execute("UPDATE asset_paths SET seen_at=?, mtime=? WHERE path=?", (now(), st.st_mtime, key))
            c.execute("UPDATE assets SET mtime=? WHERE id=?", (st.st_mtime, row["id"]))
        return "unchanged", row["id"]
    ch = content_hash(lp, on_hash) if on_hash else content_hash(lp)
    with db.tx() as c:
        # Folder scans and uploads can finish hashing the same bytes together.
        # Check under the write lock so only one asset is created across sources.
        # A folder may have been excluded while this file was being hashed.
        if is_excluded(db, key):
            return "excluded", None
        dup = c.execute("SELECT id, path, status FROM assets WHERE content_hash=? AND deleted_at IS NULL", (ch,)).fetchone()
        if dup and (row is None or row["id"] != dup["id"]):
            # Same bytes already known under another path: record the extra location only.
            if row:
                c.execute("DELETE FROM asset_paths WHERE path=?", (key,))
            c.execute("INSERT OR REPLACE INTO asset_paths(asset_id, path, mtime, size, seen_at) VALUES(?,?,?,?,?)",
                      (dup["id"], key, st.st_mtime, st.st_size, now()))
            if dup["status"] == "missing" or (not Path(dup["path"]).exists() and not str(dup["path"]).startswith("s3://")):
                c.execute("UPDATE assets SET path=?, filename=?, status=CASE WHEN status='missing' THEN 'new' ELSE status END WHERE id=?",
                          (key, name, dup["id"]))
            return "duplicate", dup["id"]
        if row:
            # File at a known path changed content: keep identity, reset processing.
            c.execute("UPDATE assets SET size=?, mtime=?, quick_hash=?, content_hash=?, local_path=?, status='new', updated_at=?, deleted_at=NULL WHERE id=?",
                      (st.st_size, st.st_mtime, qh, ch, None if str(lp) == key else str(lp), now(), row["id"]))
            c.execute("UPDATE asset_paths SET mtime=?, size=?, seen_at=? WHERE path=?", (st.st_mtime, st.st_size, now(), key))
            return "changed", row["id"]
        uid = new_uid("a")
        status = "new"
        cur = c.execute(
            "INSERT INTO assets(uid, source_id, path, filename, local_path, size, mtime, quick_hash, content_hash, status, priority, created_at, updated_at, summary)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, source_id, key, name, None if str(lp) == key else str(lp), st.st_size, st.st_mtime, qh, ch, status, priority, now(), now(),
             dumps({})))
        aid = cur.lastrowid
        c.execute("INSERT INTO asset_paths(asset_id, path, mtime, size, seen_at) VALUES(?,?,?,?,?)", (aid, key, st.st_mtime, st.st_size, now()))
        return "added", aid


def add_source(db: Database, uri: str, watch: bool = True, priority: int = 0, options: dict | None = None) -> int:
    kind = "s3" if uri.startswith("s3://") else "folder"
    if kind == "folder":
        uri = str(Path(uri).expanduser().resolve())
    # Import workers can reach the same new folder together. Keep lookup,
    # creation and option merging in one write transaction across connections.
    with db.tx() as c:
        row = c.execute("SELECT id,kind,options FROM sources WHERE uri=?", (uri,)).fetchone()
        if row:
            if row["kind"] == "photos" and kind == "folder":
                # A folder can contain both photographs and videos. An explicit
                # video import enables video watching without replacing photo records.
                c.execute("UPDATE sources SET kind='folder',watch=?,priority=? WHERE id=?",
                          (int(watch), priority, row["id"]))
            if options is not None:
                existing = loads(row["options"], {})
                c.execute("UPDATE sources SET options=? WHERE id=?", (dumps({**existing, **options}), row["id"]))
            return row["id"]
        cur = c.execute("INSERT INTO sources(uri, kind, watch, priority, options, created_at) VALUES(?,?,?,?,?,?)",
                        (uri, kind, int(watch), priority, dumps(options or {}), now()))
        return cur.lastrowid


def scan_lock(db: Database, source_id: int) -> FileLock:
    return FileLock(str(Path(db.path).parent / f"scan-{source_id}.lock"), timeout=0)


def scan_status(db: Database, source_id: int) -> dict:
    return loads(db.get_meta(f"scan:{source_id}"), {})


def queue_scan(db: Database, source_id: int) -> bool:
    """Reserve one durable request. The runtime also resumes it after a restart."""
    if not db.q1("SELECT id FROM sources WHERE id=?", (source_id,)):
        raise KeyError(source_id)
    try:
        with scan_lock(db, source_id):
            if scan_status(db, source_id).get("state") == "queued":
                return False
            db.set_meta(f"scan:{source_id}", dumps({"state": "queued", "updated_at": now()}))
            return True
    except Timeout:
        return False


def scan_source(db: Database, source_id: int, cache_dir: Path | None = None,
                on_asset: Callable[[int], None] | None = None) -> ScanResult:
    """Persist discovery/hash progress and queue each file without waiting for the whole tree."""
    try:
        with scan_lock(db, source_id):
            return _scan_source(db, source_id, cache_dir, on_asset)
    except Timeout:
        return ScanResult(asset_ids=[])


def _scan_source(db: Database, source_id: int, cache_dir: Path | None, on_asset) -> ScanResult:
    src = db.q1("SELECT * FROM sources WHERE id=?", (source_id,))
    if not src:
        raise KeyError(source_id)
    res = ScanResult(asset_ids=[])
    state = {"state": "discovering", "started_at": now(), "finished_at": None,
             "directories": 0, "found": 0, "processed": 0, "errors": 0,
             "issues": [], "current_path": src["uri"], "bytes_read": 0, "file_bytes": 0}
    last_save = 0.0

    def save(force=False):
        nonlocal last_save
        if force or time.monotonic() - last_save >= 0.5:
            last_save = time.monotonic()
            state.update({k: v for k, v in res.as_dict().items() if k != "asset_ids"})
            state["updated_at"] = now()
            db.set_meta(f"scan:{source_id}", dumps(state))

    def issue(error):
        state["errors"] += 1
        if len(state["issues"]) < 20:
            state["issues"].append(str(error))
        save()

    def directory(path):
        state["directories"] += 1
        state["current_path"] = str(path)
        save()

    def hashed(size):
        state["bytes_read"] = size
        save()

    save(True)
    seen: set[str] = set()
    try:
        if src["kind"] == "s3":
            from .s3 import iter_s3_videos
            assert cache_dir is not None
            items: Iterable[tuple[str | Path, Path]] = iter_s3_videos(src["uri"], cache_dir)
        else:
            root = Path(src["uri"])
            if not root.exists():
                raise FileNotFoundError(f"Source is unavailable: {root}. Reconnect the drive and rescan.")
            paths = []
            for path in iter_videos(root, directory, issue, excluded=excluded_folders(db)):
                paths.append(path)
                state["found"] += 1
                save()
            items = ((p, p) for p in paths)
        state["state"] = "registering"
        save(True)
        for canonical, local in items:
            if src["kind"] == "s3":
                state["found"] += 1
            state.update(current_path=str(canonical), bytes_read=0, file_bytes=0)
            save(True)
            try:
                state["file_bytes"] = Path(local).stat().st_size
                outcome, aid = register_file(db, str(canonical), source_id, src["priority"],
                                             local_path=Path(local), on_hash=hashed)
                seen.add(str(canonical))
                field = "duplicates" if outcome == "duplicate" else outcome
                setattr(res, field, getattr(res, field) + 1)
                if outcome in ("added", "changed") and aid:
                    res.asset_ids.append(aid)
                # Also recover files registered just before an interrupted scan.
                if aid and on_asset:
                    on_asset(aid)
            except Exception as e:
                log.warning("cannot ingest %s: %s", canonical, e)
                issue(f"{canonical}: {e}")
            state["processed"] += 1
            save()
    except Exception as e:
        issue(e)
        state.update(state="failed", finished_at=now())
        save(True)
        raise
    # Files that disappeared from this source.
    if src["kind"] == "folder" and not state["errors"]:
        for r in db.q("SELECT p.path, p.asset_id FROM asset_paths p JOIN assets a ON a.id=p.asset_id WHERE a.source_id=? AND a.deleted_at IS NULL AND a.media_kind='video'", (source_id,)):
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
    state.update(state="completed_with_errors" if state["errors"] else "completed", finished_at=now(), current_path="")
    save(True)
    return res
