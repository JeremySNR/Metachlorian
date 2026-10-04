# Roadmap: from a strong build to a product a team trusts

Status: proposed, 2026-10-04; item 1 delivered. Companion to [PLAN.md](../PLAN.md) (what was built) and
[OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) (what needs a human).

Eight pieces of work, chosen after reading the code, the evaluation and both review passes. Each section says what
"done" means, how it fits the code that exists, the steps in order, how it is tested, and what only a maintainer can do.
Sizes are working days for one engineer who knows the repo.

| # | Work | Size | Needs from a maintainer | Unblocks |
|---|---|---|---|---|
| 1 | Rights invariants and a real test floor | 4–5 d | nothing | everything below |
| 2 | GPU tier: hardware proxies, GPU runtime, measured numbers | 4–6 d | a machine with a GPU | 4 (VLM captions), 8 |
| 3 | Operations: backup, doctor, metrics, login throttling, worker registry | 4–5 d | nothing | 5 (worker registry) |
| 4 | Agent surface: collection tools, typed outputs, error semantics | 3–4 d | nothing | 6 (`search_moments`) |
| 5 | Remote workers | 8–10 d | a second machine to test on | team tier |
| 6 | Meaning-level speech and on-screen text search, as moments | 6–8 d | Hugging Face access for the weights (Q10) | — |
| 7 | Near-duplicates, takes and provenance | 5–6 d | nothing | — |
| 8 | A credible evaluation base | 3 d setup, then ongoing | footage licensing, a self-hosted runner | honest numbers for 2, 6, 7 |

Order of delivery: **1 → 2 and 3 in parallel → 4 → 5 → 6 → 7**, with 8 started after 1 and running alongside.
1 comes first because every later item changes the search engine, the worker or the export paths, and today those have
almost no regression coverage. 5 (remote workers) sits after 3 because it reuses the worker registry and metrics.

---

## 1. Rights invariants and a real test floor

### Done means

- No code path can return a blocked shot's media or record outside the rules, and a test proves it for every exit:
  search, similar (by shot, image and clip), `export_clip` in every mode, `build_package`, the `/media/` route and
  every MCP tool, for every role and scope combination.
- Queue, planner, cursor pagination, facets and auth each have unit tests.
- CI fails when a search-quality or shot-boundary metric drops below a floor, with no external footage.
- Coverage is reported and has a floor (start at the measured number, raise it with each item below).

### How it fits

- `core/tests/conftest.py` already synthesises footage with ffmpeg's `lavfi` sources and runs the pipeline without
  models (`processed` fixture in `test_records_rights_search.py`). Promote `processed` to `conftest.py` and add a
  **rights matrix fixture**: five copies of the sample clip with rights `cleared`, `editorial_only`, `not_cleared`,
  `expired` and empty (unknown), plus one shot-level override on the cleared file.
- Rights are evaluated in three places with slightly different logic: `search/engine.py` (`hide_blocked`,
  `BLOCKED_BADGES`, intended-use verdicts), `service.py` (`export_clip`, `build_package`) and `exports/package.py`
  (per-item worst verdict). Pull the "is this shot blocked for this principal, mode and intended use" decision into one
  function in `rights.py` (`gate(doc_rights, *, principal, mode, intended) -> Verdict`) and call it from all three, so
  the tests pin one function and the three callers only test wiring.

### Steps

1. **Fixtures.** Move `processed` to `conftest.py`; add `rights_matrix` (returns the five asset uids and one shot uid
   per asset) and `principals` (viewer, editor, admin, agent-default, agent+export, agent+collections, agent+tags,
   local admin). Add a `mcp_client` fixture that connects an in-memory MCP client session to `build_server(lib)`.
2. **Rights gate.** Add `rights.gate` and route the three callers through it. Behaviour must not change; the
   existing tests are the check.
3. **Invariant tests** (`tests/test_rights_invariants.py`), parametrised over principal × exit path × rights state:
   - search with default `hide_blocked` never returns `not_cleared` or `expired`; `hide_blocked=False` returns them
     with a `rights.verdict` of `blocked`;
   - search with `intended_use` returns only `allowed` unless `include` asks for more;
   - `find_similar` by shot, by image bytes and by clip applies the same rule (fresh-review finding 2);
   - `export_clip` refuses `proxy`, `original` and timeline modes for blocked shots for everyone, and refuses
     non-`allowed` verdicts for agents when an intended use is given; `reference` mode is allowed;
   - `build_package` for an agent is refused unless every item is `allowed` or `allow_restricted` is set, and the
     refused package directory is removed;
   - the `/media/{asset}/…` route serves proxies to people with `library:read` and to agents only when the shot is not
     blocked (decide and document; today it is unchecked);
   - every MCP tool returns a tool error, not data, when the scope is missing.
4. **Queue tests** (`tests/test_queue.py`): `claim` honours `resources`; a lease that expires is re-queued and the late
   `commit` is a no-op (the `cur_job["status"] != "running"` branch); `fail` backs off `10 * 2**attempts` and stops at
   `MAX_ATTEMPTS`; `requeue_expired` counts.
5. **Planner tests** (`tests/test_planner.py`): bumping an analyser's `version` or `config()` changes its input key and
   its dependants' keys only; an `Unavailable` analyser becomes `done` after the model appears and `plan_all` picks it up;
   a changed file re-plans everything; an unchanged file plans nothing.
6. **Search tests** (`tests/test_search_engine.py`): cursor round-trip and a cursor from another query is ignored;
   facets count only the filtered pool; `strictness` thresholds split strong/weak as documented; folder and collection
   scopes compose with filters; `limit` bounds; an empty query with a scope orders by quality.
7. **Auth tests**: CSRF header rule for cookie sessions; loopback rule in solo mode (host and client both loopback);
   expired and revoked tokens; token scopes never widen past the role.
8. **CI gates.** Replace the placeholder step in `.github/workflows/ci.yml` with `python eval/ci_gates.py`, which:
   builds a synthetic shot-boundary gold set from `lavfi` sources (cuts, dissolves via `xfade`, fades, a flash decoy)
   and asserts F1 ≥ 0.85; renders the motion gold set from generated stills and asserts ≥ 36/40; runs the parser spec
   queries. Add `pytest-cov` to the `dev` extra, upload the report and fail under the floor.

### Size and risks

4–5 days. The rights-gate refactor touches the hottest path in `engine.py`; do it with the invariant tests already
written against the current behaviour so the refactor is a pure move.

### Delivered

Status: **done**. `rights.gate` (and `rights.range_gate` for time ranges) decides for every exit;
`tests/test_rights_invariants.py` pins it, and a mutation check (disabling each rule in turn) makes at least one case fail
every time. An independent review then found range and download leaks, closed in the same PR (below). The invariant tests found holes
that the "pure move" could not keep, so behaviour changed in these places:

- **Packages with blocked footage are refused for everyone**, as clip exports already were. Before, a person could
  package not-cleared or expired shots with media and thumbnails.
- **Refusals happen before anything is rendered.** Before, an agent's refused package was rendered, then deleted, and
  with `zip` its `.zip` stayed in the export folder, downloadable through `/api/exports/file`.
- **`allow_restricted` never admits blocked items** (it admitted any verdict; it is not exposed over REST or MCP).
- **`/media/` for agents** (the decision this item asked for): these files cover the whole file, so stills are refused
  when any shot is blocked and video unless every shot is cleared as recorded; an id not in the library is a 404. People
  with `library:read` still see everything, because reviewing footage is how its rights get fixed.
- **Clip in/out reaching past the shot**: `export_clip` checked only the named shot, so its in/out could cut a blocked
  neighbour. Every shot the range covers is now checked, and package handles stop at a neighbour that may not leave.
- **Downloads re-check rights**: every export gets a record of the ranges it holds; `/api/exports/file` re-checks them
  against the rights as they are now, and agents can download only their own exports.
- **Media leaves today**: an intended-use `date` no longer releases a licence that has not started yet.
- **Search results carry `rights.verdict: blocked`** with reasons when blocked footage is shown (`hide_blocked=false`).
- **A restricted licence past its expiry is `expired`** (the badge said `restricted`, so it was not treated as blocked).
- **MCP failures are tool errors** (`isError: true`, text `"<Type>: <message>"`), as ADR 011 specified, instead of an
  `{"error": …}` result. This is also item 4's error-semantics step.
- **Solo mode over `http://[::1]/`** (IPv6 loopback without a port) was refused because the Host header was mis-parsed.

Also added: queue, planner, search-engine and auth unit tests; shared fixtures in `conftest.py` (`processed`,
`rights_matrix`, `principals`, `mcp_client`); a coverage floor of 68 % (measured 69 %) in `core/pyproject.toml`; and
`eval/ci_gates.py` in CI (see `eval/README.md`).

---

## 2. GPU tier: hardware proxies, GPU runtime, measured numbers

### Done means

- Proxy transcoding uses NVENC, VideoToolbox, VAAPI or Quick Sync when present, with automatic fallback to `libx264`.
- A `metachlorian[gpu]` install and a `Dockerfile.cuda` image run ONNX models and the optional VLM on the GPU.
- `/api/health` and Settings → Processing show which encoders and ONNX providers are active.
- `eval/README.md` has a GPU column with measured throughput, VLM caption accuracy and shot-size accuracy.

### How it fits

- `media/ffmpeg.py::make_proxy` hard-codes `libx264 -preset veryfast -crf 26`. `models.py::session` already asks ONNX
  Runtime for CUDA, CoreML or DirectML providers, so model acceleration is an install problem, not a code problem.
- The proxy encoder must **not** be part of the `proxy` analyser's `config()`, or installing a GPU would re-encode
  every proxy in the library. Record the encoder used in the run output instead.
- Analysis decoding (`iter_frames`, `frame_at`) stays on the CPU decoder: shot detection is deterministic and the
  gold set was tuned on software-decoded frames. Hardware decode changes pixel values slightly.

### Steps

1. **Encoder detection.** `ffmpeg.detect_encoders()` parses `ffmpeg -encoders` once per process and probes each
   candidate with a 1-second `lavfi` encode so a listed-but-broken encoder (no device, driver mismatch) is skipped.
   Cache the result in `<data_dir>/cache/encoders.json` with the ffmpeg version as key.
2. **Encoder table** in `make_proxy`, matched for quality to `crf 26`:
   - `h264_nvenc`: `-preset p4 -rc vbr -cq 26 -b:v 0`
   - `h264_videotoolbox`: `-q:v 55 -realtime 0`
   - `h264_vaapi`: `-vaapi_device /dev/dri/renderD128`, `-vf …,format=nv12,hwupload`, `-qp 26`
   - `h264_qsv`: `-global_quality 26 -look_ahead 0`
   Keep the 1 s GOP, `fps_cap` and scale filter. On a non-zero exit, log once per encoder and retry with `libx264`.
3. **Setting** `proxy_encoder = "auto" | "cpu" | <name>` in `config.py`, editable from Settings → Processing.
   `render_clip` uses the same table for exports (quality `cq 18` equivalents).
4. **Packaging.** Add `gpu = ["onnxruntime-gpu>=1.19"]` to `pyproject.toml` (mutually exclusive with `onnxruntime`;
   `scripts/install.sh` picks one after detecting `nvidia-smi`). Add `Dockerfile.cuda` from
   `nvidia/cuda:12.6-runtime-ubuntu24.04` with a static ffmpeg build that includes `h264_nvenc` (BtbN builds) and
   `sherpa-onnx` CUDA wheels from their index. Publish as `ghcr.io/jeremysnr/metachlorian:cuda` from
   `release.yml`.
5. **Worker placement.** `start_background` keeps one `model` worker. Add a `gpu_workers` setting (default 1 when a
   GPU provider is active) so a multi-GPU host can run several model workers; `claim` already filters by resource.
6. **VLM profile.** Turn the commented `vlm` service in `deploy/docker-compose.yml` into `profiles: ["vlm"]`, add
   `metachlorian models fetch --vlm qwen3.5-4b` to download the GGUF and `mmproj` into the models volume, and have
   the entrypoint set `vlm.base_url` when the service is reachable.
7. **Report.** `health()` returns `{"encoders": [...], "onnx_providers": [...], "vlm": {...}}`; the Processing page
   shows them under the worker list.
8. **Measure** (maintainer, on a GPU box): `eval/throughput.sh --label gpu`, then `eval/content/evaluate.py` on the
   VLM-captioned library for shot size, setting and caption quality; fill the GPU row in `README.md` and
   `eval/README.md`.

### Size and risks

4–6 days of engineering plus a day of measurement on real hardware. VAAPI device paths and Docker GPU pass-through
vary by host; ship `cpu` fallback and a `doctor` check (item 3) rather than trying to cover every driver.

---

## 3. Operations: backup, doctor, metrics, login throttling, worker registry

### Done means

- `metachlorian backup` and `restore` exist, are documented, and a restored library searches identically.
- `metachlorian doctor` finds the common misconfigurations and says how to fix them.
- `/metrics` exposes Prometheus text for jobs, analyser time, search latency and workers.
- Repeated login failures are slowed and audited.
- Workers register themselves; the Processing page shows who is alive and what each is doing.

### Steps

1. **Backup.** `cli.cmd_backup(dest)`: `VACUUM INTO` a temp file (consistent snapshot under WAL), then tar it with
   `index/` (the usearch and int8 caches; cheap to rebuild but slow at 1 M shots) and `config.toml`. Never include
   the provider key files by default; `--with-keys` opts in. `restore` unpacks and runs `migrate()` and a vector-index consistency
   check (`VectorIndex.sync` from watermark 0 if the cache is older than the DB). Settings `backup.dir`, `backup.keep`
   and a nightly timer in the `_watch` thread.
2. **Doctor.** `cli.cmd_doctor`: ffmpeg and exiftool present and versions; encoders (item 2) and ONNX providers;
   each `ModelSpec` installed or missing with the fetch command; `PRAGMA integrity_check`; disk free on data, media and
   export dirs; jobs `running` with a stale lease; `failed` jobs grouped by error; vector cache age versus DB; whether
   `require_auth` is off while listening on a non-loopback host. Exit code 1 on any failure.
3. **Metrics.** `api/app.py` `GET /metrics` behind `admin` scope or a token with a new `metrics:read` scope. No new
   dependency: write the exposition format by hand. Series: `jobs{status,analyser}` gauge; `analyser_seconds`
   histogram from `analysis_runs` (`finished_at - started_at`, bucketed); `search_latency_seconds` histogram kept in
   process by `Library.search`; `queue_oldest_age_seconds`; `workers_alive`; `assets{status}`; `shots_total`;
   `vectors{space}`. Wire `METACHLORIAN_LOG_FORMAT=json` into `logging.basicConfig` with a request-id filter.
4. **Login throttling.** Table `login_failures(key, count, until)` keyed by `username` and by client address.
   After 5 failures in 15 minutes, delay the response `min(2**n, 30)` seconds; after 10, refuse until the window
   ends. Write `login_locked` to the audit log. Clear on success. Test with a frozen clock.
5. **Worker registry.** Table `workers(id, host, resources, started_at, last_seen, job_id)`. `pipeline.Worker`
   upserts on start and on every `heartbeat`. `stats()` joins it so `/api/processing` lists workers; stale rows
   (no heartbeat for 3 × `LEASE_S`) are shown as lost and pruned. This is the table remote workers (item 5) register in.
6. **Metadata export and import.** `metachlorian export-metadata out.jsonl` writes assets, shots, signals,
   corrections, rights, collections and identities keyed by content hash; `import-metadata` merges corrections and
   rights by content hash and reports conflicts. This is how a library moves between machines without re-analysis and
   how two libraries share rights records.

### Size and risks

4–5 days. Backup must be tested against a library mid-analysis (writers active) to prove the snapshot is consistent.

---

## 4. Agent surface: collection tools, typed outputs, error semantics

### Done means

- An agent with `collections:write` can create a collection, add and remove shots and set in/out and notes.
- Every tool declares an `outputSchema` and returns structured content that validates against it.
- Tool failures surface as MCP tool errors (`isError: true`) with actionable text, not as data payloads.
- The REST API publishes the same models in OpenAPI, and `app/src/api/types.ts` is generated from it.

### How it fits

- `mcp_server/server.py` returns `dict[str, Any]` from every tool, so the SDK emits no output schema, and `_err`
  returns an error as an ordinary result. `schemas/__init__.py` is empty and was clearly meant for this.
- `service.py` already has `create_collection`, `add_to_collection`, `update_item`, `reorder` and `remove_item`;
  the MCP layer simply never exposed them.

### Steps

1. **Models.** In `schemas/`, define Pydantic models for `SearchResult`, `SearchResponse`, `ShotRecord`,
   `AssetRecord`, `RightsVerdict`, `Collection`, `CollectionItem`, `PackageResult`, `ExportResult`, `Person`,
   `Folder`, `LibraryStats`, `Vocabulary`. Build them from the dicts the service returns (`model_validate`) so the
   service does not change in this step. Add a test that validates a real response from every service method.
2. **Tools.** Return the models from each MCP tool; the SDK derives `outputSchema` and emits `structuredContent`
   plus the JSON text. Replace `_err` with raising `mcp.server.mcpserver.ToolError` (or the SDK's equivalent) so
   clients see `isError`. Add tools `create_collection`, `add_to_collection`, `update_collection_item`,
   `remove_from_collection`, all annotated `WRITE`, all requiring `collections:write`; no delete tool for agents.
   Give `find_similar` a `cursor`.
3. **REST parity.** Set `response_model` on the FastAPI routes to the same models. Generate
   `app/src/api/types.generated.ts` with `openapi-typescript` in `npm run build` and migrate `types.ts` to re-export
   it (one feature at a time; the compiler finds the mismatches).
4. **Agent task suite.** `core/tests/test_agent_flows.py`: scripted tool sequences over the in-memory MCP client
   that mirror `docs/agents.md` (brief → search → check_rights → build_package; folder scope → similar → collection),
   asserting scopes, structured output validity and a schema-valid package. This is the regression net for item 6's
   `search_moments` and item 7's `collapse`.
5. **Docs.** Update `docs/agents.md` tool table and ADR 011 status.

### Size and risks

3–4 days. The MCP SDK's structured-output API changed across 2026 releases; pin `mcp` in `pyproject.toml` and check
`outputSchema` appears in `tools/list` in the test.

---

## 5. Remote workers

### Done means

- `metachlorian worker --server https://nas:8765 --token mc_… [--resources cpu,model] [--media-root /Volumes/footage]`
  runs analysis on another machine against a library served elsewhere, with identical output to a local worker.
- The server can run with `workers = 0` and only ingest, search and serve.
- Workers appear in the registry (item 3) and jobs they hold are re-queued when they vanish.

### How it fits

- The queue is already lease-based with heartbeats, and `pipeline.commit` already refuses a commit from a lost lease,
  so the server-side state machine needs no change.
- The obstacle is `AnalysisContext`: it reads the DB directly (`shots()`, `signals_of`, `output_of`, `tech`) and
  writes files into `settings.media_dir / asset_uid`. Analysers themselves only use the context, so one seam fixes
  everything.

### Steps

1. **Context seam.** Split `AnalysisContext` into the public surface analysers use and a `Backend` protocol with
   `LocalBackend(db, settings)` (today's code) and `RemoteBackend(client, job_bundle, scratch_dir)`. The remote
   backend answers reads from a bundle fetched at claim time and stages writes in `scratch_dir`.
2. **Worker API** (`api/workers.py`, scope `jobs:run`, new role `worker`):
   - `POST /api/workers/claim` `{worker_id, resources}` → job, asset row, the shots list, this asset's signals and
     run outputs for the analyser's `requires`, the settings subset the analyser's `config()` reads, and a media
     manifest (which work-dir files exist, with sizes and hashes);
   - `POST /api/workers/jobs/{id}/heartbeat`;
   - `GET /api/workers/assets/{uid}/source` streams the original (used only when `--media-root` is not given);
   - `GET /media/{uid}/{file}` (exists) for proxy and keyframes the analyser needs;
   - `POST /api/workers/jobs/{id}/commit` multipart: `result.json` (status, output, signals, moments, new shots,
     keyframe updates, asset updates, faces), `vectors.npz`, and changed work-dir files as parts. The server writes
     files into the work dir, then calls `pipeline.commit` in one transaction; `attempts`, `error` and lease checks
     behave exactly as locally.
3. **Worker CLI.** `cli.cmd_worker`: registers in `workers`, loops claim → run → commit with the same backoff as
   `Worker.loop`, heartbeats from a thread, and on `Unavailable` commits `unavailable` with the reason. Config lives
   in `~/.config/metachlorian/worker.toml` (server, token, media root mapping, resources, concurrency).
4. **Media access modes.** `--media-root` maps the server's source paths onto a local mount (fast, the common NAS
   case); without it the worker streams the source once into scratch and deletes it after commit.
5. **Settings propagation.** The claim response carries the settings subset; a worker never reads the server's
   `config.toml`. `endpoint_allowed` for VLM/LLM is evaluated server-side and passed as a flag so a worker cannot be
   used to bypass the egress rule.
6. **Tests.** `tests/test_remote_worker.py` runs the FastAPI app in-process with the ASGI client, a `Worker` on
   `RemoteBackend` over it, and asserts every signal, moment, vector and file equals a `LocalBackend` run on the same
   clip (parity). Lease loss mid-job and a commit after the lease expired are tested the same way as item 1 step 4.
7. **Docs and compose.** `docs/architecture.md` gains a deployment diagram with a NAS core and a GPU worker;
   `deploy/docker-compose.worker.yml` for the worker image.

### Size and risks

8–10 days. The parity test is the heart of it; write it first against `LocalBackend` so the refactor in step 1 is
checked before any HTTP exists. Large source files over HTTP are slow; the media-root mode is the one to recommend.

---

## 6. Meaning-level speech and on-screen text search, as moments

### Done means

- "The part where he talks about missing his family" finds the utterance, not just shots whose transcript shares
  words with the query, in the 25 languages Parakeet covers.
- Search can return **moments** (a shot uid plus in/out and the matched text) as well as shots, in REST, MCP and the app.
- Descriptive visual queries score the same as today on the pooled judgments.

### How it fits

- `analysers/text_embed.py` embeds transcript + caption + OCR per shot with SigLIP's text tower, and the engine
  ignores it (`FUSE_TEXT_SPACE = False`) because it is not a sentence encoder. This analyser is replaced, not added to.
- `vectors` rows are keyed by `shot_id`; moments need their own key. `moments` already holds utterances with word
  timings (`kind='speech'`) and OCR spans (`kind='text'`).
- `engine._result` already snaps in/out to a keyword-matching moment; semantic moments generalise that.

### Steps

1. **Model.** `scripts/export_e5.py` exports `intfloat/multilingual-e5-small` (MIT, 384-d) to ONNX int8 with its
   tokenizer, and `models.py` gains `ModelSpec("e5-small-multilingual", …)` pointing at the `models-v1` release asset.
   A maintainer with Hugging Face access runs the export and uploads it (same route as the SigLIP asset, Q4).
   `media/textenc.py` wraps it with the `query: ` / `passage: ` prefixes the model expects.
2. **Schema.** Migration v6: `ALTER TABLE vectors ADD COLUMN moment_id INTEGER` with an index on `(space, moment_id)`.
   `VectorIndex` keeps `moment_of: dict[int, int | None]` alongside `shot_of`, and `search()` returns
   `(shot_id, moment_id, score)` with `_best_per_shot` choosing the best moment per shot.
3. **Analyser.** Rewrite `text_embed` as version 2.0.0 using e5: one `text` vector per shot (transcript + OCR, no
   template captions) for "similar by transcript", plus one `speech_sem` vector per **window** of speech moments
   (consecutive utterances merged to 12–40 words so single short lines still carry meaning) and one `text_sem`
   vector per OCR moment. The version bump re-runs it library-wide on upgrade; nothing else re-runs.
4. **Engine.** New retriever lists `speech_sem` and `text_sem` in the fusion step, query embedded once with e5.
   Start at weight 0.9 and tune on the new eval set (step 7). Add `granularity: "shot" | "moment"` to `SearchRequest`:
   at `moment` granularity a shot may appear several times with different in/out and each result carries
   `moment: {kind, start, end, text, score}`; at `shot` granularity the best semantic moment becomes the snapped in/out
   when no keyword moment exists. Match strength for semantic-only hits: calibrate cosine against the judgments so
   `strong` means the same thing as for visual hits.
5. **API and MCP.** `GET /api/search?granularity=moment`; a `search_moments` MCP tool (same arguments as
   `search_shots`, returns moments) so agents can ask for "the line where…" directly. The query parser treats
   `said:`/`says:` and quoted phrases as speech-intent hints that raise the speech weights.
6. **App.** Result cards at moment granularity show the matched line and its timecode under the thumbnail, and the
   player opens at the moment's start. A `Moments` toggle in the search bar sets the granularity in the URL.
7. **Eval.** `eval/search/paraphrase.py`: 40 hand-written paraphrases of transcript lines in the demo library (none
   sharing a content word with the line), targets are moments; report MRR@10 and whether the returned in/out overlaps
   the target by ≥ 50 %. Re-run `relevance.py` and `known_item.py` and require no regression. Resolve Q10.

### Size and risks

6–8 days plus the weights upload. The analyser re-run is the only expensive part for existing libraries; at the
measured speech throughput it is minutes, not hours, because it embeds text, not audio.

---

## 7. Near-duplicates, takes and provenance

### Done means

- Byte-different copies of the same footage (re-exports, transcodes, trims, letterboxed versions) are linked as
  duplicates; results show one representative with a "+n" stack unless asked otherwise.
- Shots of the same set-up (an interview angle, repeated takes) are grouped, and the group is a facet and a
  collapse option.
- A finished edit lists the raw files its shots came from, and a raw file lists the edits that used it.

### How it fits

- `embed` already writes a `visual` centroid and `visual_kf` per keyframe for every shot, so matching needs no new
  model. The queue is per-asset; matching is cross-library, so it is a maintenance pass, not an analyser.
- `rollup` already classifies assets as raw / selects / finished, which is what provenance needs.

### Steps

1. **Schema.** Migration v7: `shot_links(shot_id, other_id, kind, score, created_at)` with `kind IN
   ('duplicate','take','setup')` stored once per unordered pair; `shot_groups(group_id, shot_id, kind)` maintained by
   union-find; `asset_links(asset_id, source_asset_id, shots)` for provenance. `shot_index` gains `group_dup` and
   `group_take` integer columns for fast collapse in SQL.
2. **Matcher** (`linking.py`), incremental: for every `visual_kf` vector above the last processed id, query the
   `visual_kf` index for its 10 nearest neighbours in other shots; a candidate pair is scored on keyframe cosine,
   shot-centroid cosine, duration ratio, transcript similarity (token Jaccard when both have speech) and aspect/crop
   compatibility.
   - **duplicate**: ≥ 2 keyframes with cosine ≥ 0.97, duration within 10 % or one contained in the other, transcripts
     agree when present;
   - **take**: centroid cosine ≥ 0.90, same source folder or camera, capture times within 30 minutes, transcripts
     differ or absent;
   - **setup**: centroid cosine ≥ 0.88 inside one asset (the recurring interview angle).
   Run from the `_watch` loop after `plan_all` when the queue is idle, and from `metachlorian reindex`.
3. **Provenance.** When an asset's `edit_type` is `finished` or `selects`, each of its shots with a duplicate link to a
   shot in a `raw` asset adds to `asset_links`. `get_asset` returns `derived_from` and `used_in`; the Asset page shows
   them as two lists with thumbnails.
4. **Search.** `collapse: "duplicates" | "takes" | None` on `SearchRequest` (default `duplicates`): after fusion keep
   the best-ranked member per group and attach `alternates: n, group: id`; `find_similar` takes `exclude_group`.
   A `takes` facet lists groups by size for the current pool.
5. **App and MCP.** Cards show a stack glyph with the count; expanding a stack shows the alternates in place. MCP
   `search_shots` gains `collapse`, and `get_shot` returns `duplicates` and `takes` arrays. Update ADR 016 with the
   collapse step.
6. **Eval.** `eval/duplicates/make_set.py` derives variants of demo files with ffmpeg (re-encode at two bitrates,
   scale to 720p, letterbox to 4:3, trim 20 % from each end, add a watermark) and asserts duplicate precision ≥ 0.98
   and recall ≥ 0.95 at the shot level. Takes are checked on the CREMA-D set (same actor, different lines = setup).

### Size and risks

5–6 days. Thresholds tuned on the 63-file library will be too tight or too loose on others; make all three thresholds
settings and surface the match score in the UI so people can see why two shots were linked.

---

## 8. A credible evaluation base

### Done means

- The evaluation library is 30–50 hours across genres (interviews, drone, sport, phone vertical, screen captures,
  low light, archive film, non-English speech), from sources whose licences are clear, documented in
  `eval/media/SOURCES.md` with checksums.
- Held-out sets come from different source collections than tuning sets.
- Shot size (the weakest signal) has its own 300-shot gold set.
- A nightly job on a self-hosted runner re-runs every evaluation and fails on regression; PR CI runs the synthetic
  gates from item 1.

### Steps

1. **Sources.** Blender Foundation open movies (CC-BY), Wikimedia Commons CC-BY and CC0 video, Prelinger Archives
   (public domain), NASA and ESA footage, Pexels under its licence, and the owner's own footage where they agree to
   it staying local. A fetch script downloads by URL list and verifies checksums; nothing is committed.
2. **Labelling through the app.** Create an `evaluator` user; label by making corrections in the Shot view (the UI
   already exists and records actor, time and note). `eval/content/export_gold.py` pulls corrections by that actor
   into `gold.json`, so gold is produced with the product rather than a side tool and the labelling cost is the UI's
   existing keyboard flow.
3. **Query sets.** 100 visual description queries written by someone who has not seen the ranking code, 50 paraphrase
   speech queries (item 6), 40 known-item speech and 40 on-screen text phrases drawn deterministically from the new
   library. Pooled judging stays as in `search/relevance.py`; keep the contact-sheet protocol.
4. **Nightly workflow.** `.github/workflows/eval.yml` on a runner labelled `eval` with the footage cached, running
   SBD, motion, content, ASR, relevance, known-item, paraphrase, duplicates and throughput; writes `eval/results/`
   and opens a PR with the diff when a number moves by more than its noise band; fails when it drops below the floor.
5. **README.** Replace the single reference-box table with per-tier rows and the date of the last run.

### Size and risks

3 days to set up, then ongoing labelling (budget 1–2 hours per 50 shots). Licensing is the long pole (Q5); keep
anything with an unclear notice local-only as today.

---

## What this does not include, and why

- **Postgres for team mode.** ADR 002's benchmark shows SQLite holding at 1.6 M shots with a path to 10 M; remote
  workers (item 5) remove the one real single-host limit. Revisit if a team needs concurrent writers beyond one core.
- **OAuth for MCP (Q8).** An organisational choice; the scoped bearer tokens are sound and audited.
- **Camera-card structures and sidecar import.** Useful, but each format is a small, independent piece of work that
  does not change the architecture; schedule after item 7.
- **The open UI items** in `review/m4/findings.md` (sort control, select-all-by-query, captions track, the hand-rolled
  grid). Each is a day or less and can ride alongside any item above; item 7 adds the first real need for a sort.
