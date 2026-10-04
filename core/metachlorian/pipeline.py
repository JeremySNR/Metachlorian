"""Planning and running analysis.

``plan_asset`` walks the analyser DAG for one asset and enqueues every
analyser whose input key has no finished run. ``run_job`` executes one job
and commits its output atomically. ``Worker`` is the long-running loop.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Any

import numpy as np

from .analysers import registry
from .analysers.base import AnalysisContext, Analyser, Unavailable
from .config import Settings
from .db import Database, dumps, loads, now
from .jobs import queue

log = logging.getLogger(__name__)


def _asset(db: Database, asset_id: int) -> dict[str, Any] | None:
    r = db.q1("SELECT * FROM assets WHERE id=?", (asset_id,))
    return dict(r) if r else None


def upstream_keys(db: Database, asset_id: int) -> dict[str, tuple[str, str]]:
    return {r["analyser"]: (r["input_key"], r["status"]) for r in
            db.q("SELECT analyser, input_key, status FROM analysis_runs WHERE asset_id=?", (asset_id,))}


def plan_asset(db: Database, settings: Settings, asset_id: int, boost: int = 0) -> list[str]:
    """Enqueue whatever is missing or stale for this asset. Returns analysers enqueued."""
    asset = _asset(db, asset_id)
    if not asset or asset["deleted_at"] or asset["status"] in ("missing",):
        return []
    if asset["status"] == "error" and not asset["content_hash"]:
        return []
    runs = upstream_keys(db, asset_id)
    analysers = registry.all_analysers()
    enqueued: list[str] = []
    pending_keys: dict[str, str] = {}
    for a in registry.topological():
        deps_ready = True
        up: dict[str, str] = {}
        for dep in a.requires:
            if dep in pending_keys:
                deps_ready = False
                break
            r = runs.get(dep)
            if not r or r[1] not in ("done", "unavailable", "failed"):
                deps_ready = False
                break
            up[dep] = r[0]
        if not deps_ready:
            # A dependency is stale or missing: this analyser waits for it.
            pending_keys[a.name] = "pending"
            continue
        key = a.input_key(settings, asset["content_hash"] or asset["quick_hash"], up)
        r = runs.get(a.name)
        if r and r[0] == key and r[1] in ("done", "unavailable", "failed"):
            continue
        pending_keys[a.name] = key
        # A job already queued or running with the same key needs nothing.
        if queue.enqueue(db, asset_id, a.name, key, priority=asset["priority"] * 1000 + boost * 1000 + a.priority):
            enqueued.append(a.name)
        else:
            existing = db.q1("SELECT status FROM jobs WHERE asset_id=? AND analyser=? AND input_key=?", (asset_id, a.name, key))
            if existing and existing["status"] in ("done", "failed", "cancelled"):
                # Run record was cleared (e.g. reset) but an old job row remains: requeue it.
                db.x("UPDATE jobs SET status='queued', attempts=0, error=NULL, run_after=0, updated_at=? WHERE asset_id=? AND analyser=? AND input_key=?",
                     (now(), asset_id, a.name, key))
                enqueued.append(a.name)
    _ = analysers
    _update_asset_status(db, asset_id)
    return enqueued


def plan_all(db: Database, settings: Settings) -> int:
    n = 0
    for r in db.q("SELECT id FROM assets WHERE deleted_at IS NULL AND status != 'missing'"):
        n += len(plan_asset(db, settings, r["id"]))
    return n


def _update_asset_status(db: Database, asset_id: int) -> None:
    open_jobs = db.q1("SELECT COUNT(*) n FROM jobs WHERE asset_id=? AND status IN ('queued','running')", (asset_id,))["n"]
    a = db.q1("SELECT status FROM assets WHERE id=?", (asset_id,))
    if not a or a["status"] == "missing":
        return
    critical_failed = db.q1("SELECT COUNT(*) n FROM analysis_runs WHERE asset_id=? AND status='failed' AND analyser IN ('technical','proxy','shots')", (asset_id,))["n"]
    status = "error" if critical_failed else ("processing" if open_jobs else "ready")
    if a["status"] != status:
        db.x("UPDATE assets SET status=?, updated_at=? WHERE id=?", (status, now(), asset_id))


def commit(db: Database, job: dict, analyser: Analyser, ctx: AnalysisContext, status: str, output: dict[str, Any],
           error: str | None, started: float) -> None:
    aid = job["asset_id"]
    with db.tx() as c:
        cur_job = c.execute("SELECT status, worker FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if not cur_job or cur_job["status"] != "running":
            return  # lease lost; another worker owns it now
        if ctx.new_shots is not None:
            _replace_shots(c, ctx, aid)
        # Replace this analyser's previous machine output for the asset.
        c.execute("DELETE FROM signals WHERE asset_id=? AND source=?", (aid, analyser.name))
        c.execute("DELETE FROM moments WHERE asset_id=? AND source=?", (aid, analyser.name))
        ts = now()
        c.executemany(
            "INSERT INTO signals(level, target_id, asset_id, name, value, source, confidence, model_version, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            [(s.level, s.target_id, aid, s.name, dumps(s.value), analyser.name, s.confidence, analyser.version, ts) for s in ctx.signals])
        c.executemany(
            "INSERT INTO moments(shot_id, asset_id, kind, start_s, end_s, text, data, source, model_version, confidence) VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(m.shot_id, aid, m.kind, float(m.start_s), float(m.end_s), m.text, dumps(m.data), analyser.name, analyser.version, m.confidence)
             for m in ctx.moments])
        for shot_id, kfs in ctx.keyframe_updates.items():
            c.execute("UPDATE shots SET keyframes=? WHERE id=?", (dumps(kfs), shot_id))
        if ctx.vectors:
            c.execute("DELETE FROM vectors WHERE asset_id=? AND space IN (%s)" % ",".join("?" * len({v[1] for v in ctx.vectors})),
                      (aid, *{v[1] for v in ctx.vectors}))
            c.executemany("INSERT INTO vectors(shot_id, asset_id, space, dim, vec, created_at) VALUES(?,?,?,?,?,?)",
                          [(sid, aid, space, int(len(v)), np.asarray(v, dtype=np.float16).tobytes(), ts) for sid, space, v in ctx.vectors])
        if ctx.asset_updates:
            cols = ", ".join(f"{k}=?" for k in ctx.asset_updates)
            c.execute(f"UPDATE assets SET {cols}, updated_at=? WHERE id=?", (*[dumps(v) if isinstance(v, (dict, list)) else v for v in ctx.asset_updates.values()], ts, aid))
        c.execute("INSERT INTO analysis_runs(asset_id, analyser, version, input_key, status, output, error, started_at, finished_at, seconds)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(asset_id, analyser) DO UPDATE SET version=excluded.version, input_key=excluded.input_key,"
                  " status=excluded.status, output=excluded.output, error=excluded.error, started_at=excluded.started_at,"
                  " finished_at=excluded.finished_at, seconds=excluded.seconds",
                  (aid, analyser.name, analyser.version, job["input_key"], status, dumps(output), error, started, ts, ts - started))
        c.execute("UPDATE jobs SET status='done', lease_until=NULL, error=?, updated_at=? WHERE id=?", (error, ts, job["id"]))


def _replace_shots(c, ctx: AnalysisContext, aid: int) -> None:
    """Swap in a new segmentation. Shot uids are stable for unchanged starts, so
    collections keep pointing at the same shots; shot-level outputs of other
    analysers are dropped because their input keys change with the segmenter's."""
    old = {r["uid"]: r["id"] for r in c.execute("SELECT uid, id FROM shots WHERE asset_id=?", (aid,)).fetchall()}
    keep: set[int] = set()
    assert ctx.new_shots is not None
    for i, s in enumerate(ctx.new_shots):
        uid = f"{ctx.asset['uid']}-{int(s['start_frame'])}"
        if uid in old:
            sid = old[uid]
            c.execute("UPDATE shots SET idx=?, start_s=?, end_s=?, start_frame=?, end_frame=?, kind=?, transition_in=?, segmenter=?, active=1 WHERE id=?",
                      (i, s["start_s"], s["end_s"], s["start_frame"], s["end_frame"], s.get("kind", "shot"), s.get("transition_in", "cut"),
                       ctx.analyser.ident, sid))
        else:
            sid = c.execute("INSERT INTO shots(uid, asset_id, idx, start_s, end_s, start_frame, end_frame, kind, transition_in, segmenter, keyframes)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?, '[]')",
                            (uid, aid, i, s["start_s"], s["end_s"], s["start_frame"], s["end_frame"], s.get("kind", "shot"),
                             s.get("transition_in", "cut"), ctx.analyser.ident)).lastrowid
        s["id"] = sid
        keep.add(sid)
    stale = [sid for sid in old.values() if sid not in keep]
    if stale:
        q = ",".join("?" * len(stale))
        # Shots still referenced by collections are kept but deactivated.
        referenced = {r[0] for r in c.execute(f"SELECT DISTINCT shot_id FROM collection_items WHERE shot_id IN ({q})", stale).fetchall()}
        drop = [s for s in stale if s not in referenced]
        if referenced:
            c.execute(f"UPDATE shots SET active=0 WHERE id IN ({','.join('?' * len(referenced))})", list(referenced))
        if drop:
            c.execute(f"DELETE FROM shots WHERE id IN ({','.join('?' * len(drop))})", drop)
    c.execute("DELETE FROM signals WHERE asset_id=? AND level='shot' AND target_id NOT IN (SELECT id FROM shots WHERE asset_id=? AND active=1)", (aid, aid))


def run_job(db: Database, settings: Settings, job: dict) -> str:
    analyser = registry.get(job["analyser"])
    asset = _asset(db, job["asset_id"])
    if analyser is None or asset is None:
        db.x("UPDATE jobs SET status='cancelled', updated_at=? WHERE id=?", (now(), job["id"]))
        return "cancelled"
    ctx = AnalysisContext(db, settings, asset, analyser)
    started = now()
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(queue.LEASE_S / 3):
            try:
                queue.heartbeat(db, job["id"])
            except Exception:  # pragma: no cover
                pass

    hb = threading.Thread(target=beat, daemon=True)
    hb.start()
    try:
        reason = analyser.check(settings)
        if reason:
            raise Unavailable(reason)
        output = analyser.run(ctx) or {}
        commit(db, job, analyser, ctx, "done", output, None, started)
        result = "done"
    except Unavailable as e:
        commit(db, job, analyser, AnalysisContext(db, settings, asset, analyser), "unavailable", {}, str(e), started)
        result = "unavailable"
    except Exception as e:
        log.warning("%s failed on %s: %s", analyser.name, asset["filename"], e)
        log.debug(traceback.format_exc())
        if job["attempts"] < queue.MAX_ATTEMPTS:
            queue.fail(db, job, e)
            result = "retry"
        else:
            commit(db, job, analyser, AnalysisContext(db, settings, asset, analyser), "failed", {}, f"{type(e).__name__}: {e}", started)
            db.x("UPDATE jobs SET status='failed' WHERE id=?", (job["id"],))
            result = "failed"
    finally:
        stop.set()
    if result != "retry":
        from .indexer import index_asset

        try:
            index_asset(db, settings, job["asset_id"])
        except Exception:  # pragma: no cover - indexing must never block the queue
            log.exception("indexing failed for asset %s", job["asset_id"])
        plan_asset(db, settings, job["asset_id"])
    return result


class Worker:
    """Pulls jobs until stopped. Several workers (processes) can share a library."""

    def __init__(self, db: Database, settings: Settings, resources: tuple[str, ...] = ("cpu", "model"), idle_sleep: float = 1.0):
        self.db = db
        self.settings = settings
        self.resources = resources
        self.idle_sleep = idle_sleep
        self.stopped = threading.Event()
        self.ident = queue.worker_id() + ":" + "+".join(resources)

    def run_once(self) -> str | None:
        job = queue.claim(self.db, self.ident, self.resources, registry.all_analysers())
        if not job:
            return None
        return run_job(self.db, self.settings, job)

    def run_until_idle(self, max_jobs: int | None = None) -> int:
        n = 0
        while not self.stopped.is_set():
            r = self.run_once()
            if r is None:
                break
            n += 1
            if max_jobs and n >= max_jobs:
                break
        return n

    def loop(self) -> None:
        while not self.stopped.is_set():
            try:
                r = self.run_once()
            except Exception:  # pragma: no cover
                log.exception("worker error")
                r = None
            if r is None:
                self.stopped.wait(self.idle_sleep)

    def stop(self) -> None:
        self.stopped.set()


def process_until_idle(db: Database, settings: Settings) -> int:
    """Run every queued job in this process (CLI and tests)."""
    plan_all(db, settings)
    return Worker(db, settings).run_until_idle()


_ = (loads, time)
