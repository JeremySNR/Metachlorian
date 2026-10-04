# 009. Job queue for ingest and analysis

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
Ingest and analysis are long, GPU-heavy jobs: shot detection, transcription, embeddings, OCR and captioning. They run over thousands of hours of footage. The queue must be:
- **resumable**: a crash, sleep or quit mid-file loses at most one chunk;
- **idempotent**: re-running produces the same rows, never duplicates;
- **prioritised**: an interactive "analyse this now" beats a background backfill;
- **aware of analyser versions**: each analyser is versioned on its own, so bumping `ocr@3` re-queues only OCR work.

Solo mode must not need **an extra server**: no Redis, RabbitMQ, Temporal or Hatchet. Team mode runs one core on a NAS or server, with possibly several workers (CPU and GPU). The store is SQLite (WAL), with Postgres as a later backend (002). The build environment has no GPU and 4 CPUs, so tests must run CPU-only.

## Options considered
| Option | Quality / fit | Licence | Infra | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **Own table queue in the core DB** | Enqueue and result-commit happen in **one transaction** with the analysis output, so jobs are exactly-once in effect. The unique job key is `(asset, analyser, version, params_hash)`. Leases + heartbeat, priority + FIFO, per-chunk checkpoint column. | Ours (Apache-2.0) | None. SQLite now; Postgres via `FOR UPDATE SKIP LOCKED` later. | Thousands of claims per second, which is far above GPU throughput | New code, ~300-500 lines plus tests | We maintain it |
| **DBOS Transact** | Durable workflows with checkpointed steps. Queues with **priority**, concurrency limits, rate limits, dedup and timeouts. **SQLite by default**, Postgres for production ([queue docs](https://docs.dbos.dev/python/tutorials/queue-tutorial), [repo](https://github.com/dbos-inc/dbos-transact-py)). | MIT | Library only | Good | 3.2.0 (2026-09-29) ([PyPI](https://pypi.org/project/dbos/)). Major API changes in 3.0. | 1.6k★, company-backed (DBOS Inc.) |
| Huey | Simple task queue with priority, retries, locks, results and scheduling. Storage options: Redis, **SQLite**, Postgres, file, memory ([repo](https://github.com/coleifer/huey)). | MIT | Library and consumer process | Good | 3.4.0 (2026-09-04) ([PyPI](https://pypi.org/project/huey/)). Mature since 2011. | 6.0k★, essentially one maintainer |
| Procrastinate | Priority, retries, queueing locks, cancel/abort, periodic jobs, sync and async | MIT | **Postgres only** ([repo](https://github.com/procrastinate-org/procrastinate)) | Good | Stable | 1.4k★, **looking for maintainers** |
| Oban for Python | Transactional enqueue, priority, history | Apache-2.0 | Postgres 14+ only | Good | 0.6.x, first released Jan 2026 | 297★. **Unique jobs, workflows and global concurrency are paid "Pro"** ([repo](https://github.com/oban-bg/oban-py)) |
| PgQueuer | LISTEN/NOTIFY, fast | MIT | Postgres only ([repo](https://github.com/janbjorge/pgqueuer)) | Very fast | Pre-1.0 | Small team |
| Celery | Feature-rich: canvas, retries, routing | BSD-3 | Needs a broker (Redis or RabbitMQ). SQL transports are experimental; SQLAlchemy is mainly a result backend. | High | 5.6.3 (2026-03) ([docs](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/index.html)) | Huge but slow-moving. Its priority support depends on the broker. |
| RQ | Simple. Priority through queue order or enqueue-at-front. | BSD-2 | **Redis/Valkey** ([repo](https://github.com/rq/rq)) | Good | Mature | 10.7k★. Fork-based workers are awkward on Windows. |
| arq | asyncio + Redis | MIT | Redis | Good | **Maintenance-only mode** ([repo](https://github.com/python-arq/arq)) | Inactive |
| Dramatiq | Reliable actors | **LGPL-3.0** ([repo](https://github.com/Bogdanp/dramatiq)) | RabbitMQ or Redis | High | Mature | 5.3k★ |
| Hatchet | Durable tasks, priority, fair concurrency, UI | MIT | **Server + Postgres** ([repo](https://github.com/hatchet-dev/hatchet)) | 10k tasks/s | Python SDK 1.41.1 (2026-09-24) | 8.1k★, VC-backed |
| Temporal | Gold-standard durable execution | MIT | **Server cluster** in production. `start-dev` uses SQLite but is for development only ([sdk](https://github.com/temporalio/sdk-python)). | High | Very mature | 23.4k★ |

## Evidence
- **Idempotency belongs to the domain, not the broker.** "Needs analysis" is derived state: the desired `(analyser, version)` set minus completed outputs. A reconciler can rebuild the queue from the database at any time. External brokers (Celery, RQ, Dramatiq) keep jobs outside the DB, so enqueue-then-commit races and duplicate deliveries need extra dedupe logic. A table queue in the same SQLite file avoids that whole class of bug.
- **Long GPU jobs need checkpoints within a job** (e.g. per 5-minute chunk of transcript or embeddings) and lease renewal. No library gives media-chunk checkpoints for free. DBOS steps come closest, because each step is checkpointed.
- **Priority:** Huey, DBOS, Procrastinate, Oban and Hatchet support it. Celery's support depends on the broker. RQ approximates it with separate queues.
- **The "no extra server" constraint** eliminates RQ, arq, Celery, Dramatiq (they need a broker), Hatchet and Temporal for solo mode. Procrastinate, Oban and PgQueuer need Postgres, which solo mode won't have.
- **Licence:** Dramatiq's LGPL-3.0 is workable as a dependency but undesirable. Oban gates unique jobs, which are central for us, behind a paid tier.
- **Viable library candidates are DBOS and Huey.** Both use SQLite. Huey keeps its own storage separate from our records, so we lose transactional coupling. DBOS's model of workflows and steps is a good conceptual fit, but it takes over our process model and recovery semantics, has 1.6k★, and had breaking changes in 3.0.

## Decision
**Build a small table-backed queue inside the core DB**, behind a `JobQueue` interface with SQLite and (later) Postgres implementations:
- **Schema:** `jobs(id, kind, asset_id, analyser, analyser_version, params_hash, priority, state, attempts, max_attempts, run_after, lease_owner, lease_expires_at, checkpoint JSON, error, created_at, updated_at)`, with `UNIQUE(kind, asset_id, analyser, analyser_version, params_hash)`. Enqueue is `INSERT … ON CONFLICT DO NOTHING`.
- **Claim:** one `UPDATE … RETURNING` inside `BEGIN IMMEDIATE` (SQLite), or `SELECT … FOR UPDATE SKIP LOCKED` (Postgres). Order is priority, then `run_after`, then id.
- **Leases:** a lease lasts 60 s, and the worker renews it every 20 s. An expired lease returns the job to `queued` with `attempts+1`. Retries use exponential backoff and stop at `failed` (dead letter).
- **Commit:** writing outputs and marking the job done happen in one transaction. Workers write `checkpoint` per chunk, and resume from it.
- **Resources:** each worker declares slots (`gpu:1`, `cpu:N`), and jobs declare needs. This guarantees a single GPU consumer on a desktop.
- **Priority levels:** interactive 0, new ingest 10, analyser-upgrade backfill 50, maintenance 90.
- **Reconciler:** on start-up, and when an analyser version changes, it diffs desired versus completed outputs and enqueues the gaps.
- **Cancellation and pause:** a state flag that workers check between chunks.
- **API and MCP:** the queue is exposed (list, pause, cancel, re-prioritise), so admins and agents can see progress.

State machine: `queued → leased → running → (done | failed | cancelled)`.
- `paused` can be reached from `queued`.
- `blocked` means waiting on a dependency, e.g. embeddings wait for shot detection. It is a `depends_on` list resolved by the reconciler, not a workflow engine.

Rules:
- Work is processed in chunks. Each chunk's outputs are keyed by `(asset, analyser, version, chunk_index)`, so a retried chunk overwrites rather than duplicates.
- Analyser versions are semantic. Only a major or minor bump invalidates outputs; a patch bump is recorded but does not re-queue.
- Superseded outputs are kept until the new version completes for that asset, so search never goes blank during a backfill.

Test plan, in `core` tests, CPU-only:
- kill -9 a worker mid-chunk, then assert resume from checkpoint and no duplicate rows;
- two workers race for one job, and exactly one wins;
- lease expiry under a frozen clock;
- a burst of 100k enqueues with conflicts;
- reconciler diff after an analyser version bump.

DBOS is the documented fallback if multi-step workflow orchestration grows beyond simple DAGs.

## Consequences
- No broker, no extra process in solo mode, one backup file, and transactional exactly-once effects.
- We own ~500 lines of concurrency-sensitive code. It needs property tests: crash mid-job, double claim, lease expiry, and SQLite `busy_timeout` under load.
- SQLite allows one writer at a time. Fine for one core with a handful of workers; large teams need the Postgres backend.
- No built-in dashboard. The UI's admin view becomes the job dashboard.

## Revisit when
- We need durable multi-step workflows with fan-out/fan-in, sleeps or human approval steps. Re-evaluate DBOS.
- Team deployments run more than ~8 concurrent workers, or write contention shows in `SQLITE_BUSY` metrics. Move to the Postgres backend, and consider Procrastinate or Oban there.
- Distributed workers on several machines are required. Re-evaluate Hatchet or Temporal.
- The queue code passes ~1,000 lines or keeps producing concurrency bugs.
