"""Resumable, idempotent job queue in the library database.

* Enqueue is idempotent: UNIQUE(asset, analyser, input_key).
* Workers lease jobs; a crashed worker's lease expires and the job is retried.
* An analyser's output and its job's completion commit in one transaction.
* Priority = asset priority (new uploads, user requests) + analyser stage.
"""
from __future__ import annotations

import logging
import os
import socket
import time
import traceback
from typing import Any

from ..db import Database, dumps, loads, now

log = logging.getLogger(__name__)

LEASE_S = 120.0
MAX_ATTEMPTS = 3


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def enqueue(db: Database, asset_id: int, analyser: str, input_key: str, priority: int) -> bool:
    cur = db.x("INSERT OR IGNORE INTO jobs(asset_id, analyser, input_key, priority, status, created_at, updated_at)"
               " VALUES(?,?,?,?, 'queued', ?, ?)", (asset_id, analyser, input_key, priority, now(), now()))
    return cur.rowcount > 0


def requeue_expired(db: Database) -> int:
    cur = db.x("UPDATE jobs SET status='queued', worker=NULL, lease_until=NULL, updated_at=? "
               "WHERE status='running' AND lease_until < ?", (now(), now()))
    return cur.rowcount


def claim(db: Database, worker: str, resources: tuple[str, ...] | None = None, analysers: dict[str, Any] | None = None) -> dict | None:
    """Atomically take the highest-priority runnable job."""
    with db.tx() as c:
        c.execute("UPDATE jobs SET status='queued', worker=NULL, lease_until=NULL WHERE status='running' AND lease_until < ?", (now(),))
        rows = c.execute("SELECT id, analyser FROM jobs WHERE status='queued' AND run_after <= ? ORDER BY priority DESC, id LIMIT 50",
                         (now(),)).fetchall()
        for r in rows:
            if resources is not None and analysers is not None:
                a = analysers.get(r["analyser"])
                if a is None or a.resource not in resources:
                    continue
            c.execute("UPDATE jobs SET status='running', worker=?, lease_until=?, attempts=attempts+1, updated_at=? WHERE id=?",
                      (worker, now() + LEASE_S, now(), r["id"]))
            return dict(c.execute("SELECT * FROM jobs WHERE id=?", (r["id"],)).fetchone())
    return None


def heartbeat(db: Database, job_id: int) -> None:
    db.x("UPDATE jobs SET lease_until=? WHERE id=? AND status='running'", (now() + LEASE_S, job_id))


def fail(db: Database, job: dict, err: BaseException | str) -> bool:
    """Record a failure. Returns True when the job will be retried."""
    msg = err if isinstance(err, str) else "".join(traceback.format_exception_only(type(err), err)).strip()
    retry = job["attempts"] < MAX_ATTEMPTS
    db.x("UPDATE jobs SET status=?, error=?, run_after=?, worker=NULL, lease_until=NULL, updated_at=? WHERE id=?",
         ("queued" if retry else "failed", msg[-4000:], now() + (10 * 2 ** job["attempts"] if retry else 0), now(), job["id"]))
    return retry


def stats(db: Database) -> dict[str, Any]:
    out: dict[str, Any] = {"by_status": {}, "by_analyser": {}}
    for r in db.q("SELECT status, COUNT(*) n FROM jobs GROUP BY status"):
        out["by_status"][r["status"]] = r["n"]
    for r in db.q("SELECT analyser, status, COUNT(*) n FROM jobs GROUP BY analyser, status"):
        out["by_analyser"].setdefault(r["analyser"], {})[r["status"]] = r["n"]
    running = db.q("SELECT j.id, j.analyser, j.worker, j.updated_at, a.filename, a.uid FROM jobs j JOIN assets a ON a.id=j.asset_id WHERE j.status='running'")
    out["running"] = [dict(r) for r in running]
    failed = db.q("SELECT j.id, j.analyser, j.error, a.filename, a.uid FROM jobs j JOIN assets a ON a.id=j.asset_id WHERE j.status='failed' ORDER BY j.updated_at DESC LIMIT 50")
    out["failed"] = [dict(r) for r in failed]
    return out


def throughput(db: Database, window_s: float = 7 * 86400) -> dict[str, Any]:
    """Hours of new footage analysed per hour of worker activity.

    Counts files ingested and fully analysed in the window (their proxy was made in it, so
    re-analysis of old files does not inflate the figure) and divides by the time the workers
    were actually busy on them (the union of their run intervals, so idle gaps do not count)."""
    since = time.time() - window_s
    new_ids = [r["asset_id"] for r in db.q(
        "SELECT r.asset_id FROM analysis_runs r JOIN assets a ON a.id=r.asset_id"
        " WHERE r.analyser='proxy' AND r.status='done' AND r.finished_at>=? AND a.status IN ('ready','updating')", (since,))]
    per = {row["analyser"]: round(row["t"], 2) for row in db.q("SELECT analyser, SUM(seconds) t FROM analysis_runs GROUP BY analyser")}
    if not new_ids:
        return {"footage_hours": 0, "wall_hours": 0, "ratio": None, "analyser_seconds": per}
    q = ",".join("?" * len(new_ids))
    fh = db.q1(f"SELECT SUM(duration) d FROM assets WHERE id IN ({q})", new_ids)["d"] or 0
    spans = sorted((r["started_at"], r["finished_at"]) for r in db.q(
        f"SELECT started_at, finished_at FROM analysis_runs WHERE asset_id IN ({q}) AND started_at>=? AND finished_at IS NOT NULL",
        (*new_ids, since)))
    busy, cur_s, cur_e = 0.0, None, None
    for s_, e_ in spans:
        if cur_e is None or s_ > cur_e:
            if cur_e is not None:
                busy += cur_e - cur_s
            cur_s, cur_e = s_, e_
        else:
            cur_e = max(cur_e, e_)
    if cur_e is not None:
        busy += cur_e - cur_s
    wall = max(1e-6, busy / 3600)
    return {"footage_hours": round(fh / 3600, 4), "wall_hours": round(wall, 4), "ratio": round(fh / 3600 / wall, 3), "files": len(new_ids),
            "analyser_seconds": per}


_ = (loads, dumps, time, log)
