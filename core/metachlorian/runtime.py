"""Background runtime for ``metachlorian serve``: analysis worker processes,
watch-folder monitoring and periodic rescans."""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import threading
import time
import tomllib
from pathlib import Path
from typing import Any, Callable

from .config import ModelEndpoint, Settings, load_settings
from .db import Database

log = logging.getLogger(__name__)


def _worker_main(data_dir: str, resources: tuple[str, ...], stop_evt) -> None:
    logging.basicConfig(level=os.environ.get("METACHLORIAN_LOG", "WARNING"))
    from .pipeline import Worker

    settings = load_settings(data_dir)
    db = Database(settings.db_path)
    w = Worker(db, settings, resources)
    while not stop_evt.is_set():
        try:
            if w.run_once() is None:
                stop_evt.wait(1.0)
        except Exception:  # pragma: no cover
            log.exception("worker loop error")
            stop_evt.wait(2.0)


def _watch(settings: Settings, stop: threading.Event) -> None:
    """Rescan watch folders on file changes (debounced) and every 10 minutes."""
    from .ingest.scan import scan_source
    from .pipeline import plan_asset

    db = Database(settings.db_path)

    def rescan(only: set[int] | None = None) -> None:
        for s in db.q("SELECT id, kind FROM sources WHERE watch=1"):
            if only is not None and s["id"] not in only:
                continue
            try:
                res = scan_source(db, s["id"], settings.data_dir / "cache" / "s3")
                for aid in res.asset_ids or []:
                    plan_asset(db, settings, aid)
            except Exception:
                log.exception("scan of source %s failed", s["id"])

    rescan()
    last_full = time.time()
    try:
        from watchfiles import watch
    except ImportError:  # pragma: no cover
        watch = None
    while not stop.is_set():
        folders = {r["uri"]: r["id"] for r in db.q("SELECT id, uri FROM sources WHERE watch=1 AND kind='folder'")}
        existing = [p for p in folders if Path(p).exists()]
        if watch and existing:
            for changes in watch(*existing, stop_event=stop, debounce=3000, rust_timeout=60_000, yield_on_timeout=True, recursive=True):
                if changes:
                    touched = {sid for uri, sid in folders.items() if any(str(path).startswith(uri) for _, path in changes)}
                    rescan(touched)
                if time.time() - last_full > 600:
                    rescan()
                    last_full = time.time()
                new_folders = {r["uri"] for r in db.q("SELECT uri FROM sources WHERE watch=1 AND kind='folder'")}
                if new_folders != set(folders):
                    break
        else:
            stop.wait(30)
            if time.time() - last_full > 600:
                rescan()
                last_full = time.time()


def start_background(settings: Settings) -> dict[str, Any]:
    ctx = mp.get_context("spawn")
    stop_evt = ctx.Event()
    procs = []
    n = max(0, settings.workers)
    if n:
        # One worker owns the large local models; the rest do CPU analysis.
        procs.append(ctx.Process(target=_worker_main, args=(str(settings.data_dir), ("model", "cpu"), stop_evt), daemon=True))
        for _ in range(n - 1):
            procs.append(ctx.Process(target=_worker_main, args=(str(settings.data_dir), ("cpu",), stop_evt), daemon=True))
    for p in procs:
        p.start()
    tstop = threading.Event()
    t = threading.Thread(target=_watch, args=(settings, tstop), daemon=True)
    t.start()

    def stop() -> None:
        stop_evt.set()
        tstop.set()
        for p in procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()

    return {"stop": stop, "workers": len(procs)}


def save_settings(settings: Settings, changes: dict[str, Any]) -> None:
    """Apply admin changes and persist them to <data_dir>/config.toml."""
    editable = {"workers", "proxy_height", "sprite_interval", "max_segment_s", "allow_remote", "face_identity", "vlm", "llm", "require_auth"}
    for k, v in changes.items():
        if k not in editable:
            raise ValueError(f"'{k}' cannot be changed here")
        if k in ("vlm", "llm"):
            ep: ModelEndpoint = getattr(settings, k)
            for f, fv in (v or {}).items():
                if f in ("base_url", "model", "api_key_env", "local", "timeout_s", "max_images", "temperature", "extra_body"):
                    setattr(ep, f, fv)
        else:
            setattr(settings, k, v)
    cfg = settings.data_dir / "config.toml"
    current = tomllib.loads(cfg.read_text()) if cfg.exists() else {}
    for k in editable:
        val = getattr(settings, k)
        current[k] = val.__dict__ if isinstance(val, ModelEndpoint) else val
    cfg.write_text(_toml(current))


def _toml(d: dict[str, Any]) -> str:
    def fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, (list, tuple)):
            return "[" + ", ".join(fmt(x) for x in v) + "]"
        if isinstance(v, dict):
            return "{ " + ", ".join(f"{k} = {fmt(x)}" for k, x in v.items()) + " }"
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines, tables = [], []
    for k, v in d.items():
        if isinstance(v, dict):
            tables.append(f"\n[{k}]\n" + "\n".join(f"{kk} = {fmt(vv)}" for kk, vv in v.items() if vv is not None))
        elif v is not None:
            lines.append(f"{k} = {fmt(v)}")
    return "\n".join(lines) + "\n" + "".join(tables) + "\n"


_: Callable | None = None
