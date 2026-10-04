"""The job queue: leases, resources, retries with back-off, and commits from a lost lease."""
from __future__ import annotations

import pytest

from metachlorian import pipeline
from metachlorian.analysers import registry
from metachlorian.db import Database
from metachlorian.jobs import queue


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture()
def q(tmp_path, monkeypatch):
    """A migrated database with one asset row and a controllable clock for the queue."""
    clock = Clock()
    monkeypatch.setattr(queue, "now", clock)
    db = Database(tmp_path / "q.sqlite")
    db.migrate()
    db.x("INSERT INTO assets(uid, path, filename, size, mtime, quick_hash, status, created_at, updated_at)"
         " VALUES('a1', '/x.mp4', 'x.mp4', 1, 0, 'q', 'new', 0, 0)")
    yield db, db.q1("SELECT id FROM assets")["id"], clock
    db.close()


def _job(db, jid):
    return dict(db.q1("SELECT * FROM jobs WHERE id=?", (jid,)))


def test_enqueue_is_idempotent(q):
    db, aid, _ = q
    assert queue.enqueue(db, aid, "shots", "k1", 5)
    assert not queue.enqueue(db, aid, "shots", "k1", 9)
    assert queue.enqueue(db, aid, "shots", "k2", 5)  # a new input key is new work
    assert db.q1("SELECT COUNT(*) n FROM jobs")["n"] == 2


def test_claim_takes_the_highest_priority_and_leases_it(q):
    db, aid, clock = q
    queue.enqueue(db, aid, "technical", "k", 1)
    queue.enqueue(db, aid, "proxy", "k", 7)
    j = queue.claim(db, "w1")
    assert j["analyser"] == "proxy" and j["status"] == "running" and j["worker"] == "w1" and j["attempts"] == 1
    assert j["lease_until"] == clock.t + queue.LEASE_S
    assert queue.claim(db, "w2")["analyser"] == "technical"
    assert queue.claim(db, "w3") is None


def test_claim_honours_resources(q):
    db, aid, _ = q
    analysers = registry.all_analysers()
    model = next(n for n, a in analysers.items() if a.resource != "cpu")
    cpu = next(n for n, a in analysers.items() if a.resource == "cpu")
    queue.enqueue(db, aid, model, "k", 9)
    queue.enqueue(db, aid, cpu, "k", 1)
    j = queue.claim(db, "w", resources=("cpu",), analysers=analysers)
    assert j["analyser"] == cpu  # the higher-priority job needs another resource
    assert queue.claim(db, "w", resources=("cpu",), analysers=analysers) is None
    assert queue.claim(db, "w", resources=(analysers[model].resource,), analysers=analysers)["analyser"] == model


def test_claim_skips_jobs_waiting_on_back_off(q):
    db, aid, clock = q
    queue.enqueue(db, aid, "shots", "k", 1)
    db.x("UPDATE jobs SET run_after=?", (clock.t + 30,))
    assert queue.claim(db, "w") is None
    clock.t += 31
    assert queue.claim(db, "w")["analyser"] == "shots"


def test_heartbeat_extends_only_a_running_lease(q):
    db, aid, clock = q
    queue.enqueue(db, aid, "shots", "k", 1)
    j = queue.claim(db, "w")
    clock.t += 100
    queue.heartbeat(db, j["id"])
    assert _job(db, j["id"])["lease_until"] == clock.t + queue.LEASE_S
    db.x("UPDATE jobs SET status='done' WHERE id=?", (j["id"],))
    lease = _job(db, j["id"])["lease_until"]
    clock.t += 50
    queue.heartbeat(db, j["id"])
    assert _job(db, j["id"])["lease_until"] == lease


def test_an_expired_lease_is_requeued_and_counted(q):
    db, aid, clock = q
    queue.enqueue(db, aid, "shots", "k", 1)
    queue.enqueue(db, aid, "proxy", "k", 1)
    queue.claim(db, "w1")
    queue.claim(db, "w2")
    assert queue.requeue_expired(db) == 0
    clock.t += queue.LEASE_S + 1
    assert queue.requeue_expired(db) == 2
    assert {r["status"] for r in db.q("SELECT status FROM jobs")} == {"queued"}
    assert all(r["worker"] is None and r["lease_until"] is None for r in db.q("SELECT worker, lease_until FROM jobs"))


def test_claim_reclaims_an_expired_lease(q):
    db, aid, clock = q
    queue.enqueue(db, aid, "shots", "k", 1)
    first = queue.claim(db, "w1")
    clock.t += queue.LEASE_S + 1
    second = queue.claim(db, "w2")
    assert second["id"] == first["id"] and second["worker"] == "w2" and second["attempts"] == 2


@pytest.mark.parametrize("attempts", range(1, queue.MAX_ATTEMPTS + 1))
def test_fail_backs_off_then_stops(q, attempts):
    db, aid, clock = q
    queue.enqueue(db, aid, "shots", "k", 1)
    db.x("UPDATE jobs SET attempts=?", (attempts - 1,))
    j = queue.claim(db, "w")
    assert j["attempts"] == attempts
    retry = queue.fail(db, j, RuntimeError("decoder exploded"))
    row = _job(db, j["id"])
    assert "decoder exploded" in row["error"] and row["worker"] is None and row["lease_until"] is None
    if attempts < queue.MAX_ATTEMPTS:
        assert retry and row["status"] == "queued" and row["run_after"] == clock.t + 10 * 2 ** attempts
    else:
        assert not retry and row["status"] == "failed"


def test_a_commit_from_a_lost_lease_is_a_no_op(q):
    """The worker that lost its lease must not overwrite the output of the worker that took over."""
    db, aid, clock = q
    from metachlorian.analysers.base import AnalysisContext, Signal

    queue.enqueue(db, aid, "technical", "k", 1)
    job = queue.claim(db, "slow")
    clock.t += queue.LEASE_S + 1
    queue.requeue_expired(db)  # another worker could now claim it
    analyser = registry.all_analysers()["technical"]
    ctx = AnalysisContext.__new__(AnalysisContext)
    ctx.signals = [Signal("asset", aid, "late.signal", 1, 1.0)]
    ctx.moments, ctx.vectors, ctx.keyframe_updates, ctx.asset_updates = [], [], {}, {}
    ctx.new_shots, ctx.faces = None, None
    pipeline.commit(db, job, analyser, ctx, "done", {}, None, clock.t)
    assert db.q1("SELECT COUNT(*) n FROM signals")["n"] == 0
    assert db.q1("SELECT COUNT(*) n FROM analysis_runs")["n"] == 0
    assert _job(db, job["id"])["status"] == "queued"


def test_stats_group_by_status_and_analyser(q):
    db, aid, _ = q
    queue.enqueue(db, aid, "shots", "k", 1)
    queue.enqueue(db, aid, "proxy", "k", 2)
    j = queue.claim(db, "w")
    db.x("UPDATE jobs SET attempts=? WHERE id=?", (queue.MAX_ATTEMPTS, j["id"]))
    queue.fail(db, _job(db, j["id"]), "boom")
    st = queue.stats(db)
    assert st["by_status"] == {"queued": 1, "failed": 1}
    assert st["by_analyser"]["proxy"] == {"failed": 1} and st["failed"][0]["error"] == "boom"
