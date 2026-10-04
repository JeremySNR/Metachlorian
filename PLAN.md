# Metachlorian build plan

Living document. Last updated: 2026-10-04 (autonomous build session).

The build spec referred to a "Milestones and acceptance criteria" section that was not included in the copy we received
(it ends mid-way through the non-functional requirements). The milestones below are our reconstruction from the rest of the
spec; see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) Q1.

## Milestones

| # | Milestone | Acceptance criteria | Status |
|---|---|---|---|
| M0 | Research and decisions | Decision records for architecture, storage, segmentation, VLM, embeddings, speech/audio, OCR/objects/faces, camera motion, queue, vocabularies, MCP, interchange, frontend, design direction, ranking, visual review; licence table | Done (records 001–017); reconciled with what was built in M5 |
| M1 | Core data model, ingest, queue | SQLite schema with asset/shot/moment levels, every signal with value/source/confidence/model version; corrections stored separately; dedupe by content hash; resumable idempotent queue with versioned analysers; only changed analysers re-run | Done, covered by tests |
| M2 | Analysers, fusion, rollup | Deterministic shot boundaries (beats PySceneDetect on our gold set), technical metadata, camera motion, quality, loudness, audio classes, ASR with word timings, diarisation, OCR, people/faces/objects, SigLIP embeddings, zero-shot labels, VLM captions (local, optional), validated fusion, asset structure and raw/selects/finished classification | Done; accuracy, relevance and throughput in [eval/README.md](eval/README.md) |
| M3 | Search, API, MCP, exports, auth | Hybrid NL + filter + keyword + vector search with explanations, facets and rights filtering; < 500 ms median at 10k hours (benchmark); REST API; MCP server with read-only default and scopes; OTIO/FCPXML/EDL + Cutawan package validated against its schema; roles, tokens, audit log | Done. Benchmark at 1.6 M shots: median 325 ms warm; projection and memory gate for 10 M shots in ADR 002 |
| M4 | Frontend and desktop | All surfaces; keyboard-first; light/dark; tablet; WCAG 2.2 AA checks; Electron shell with solo/team modes and native drag-out | Done: web app in `app/` (React 19, TS, CSS Modules, React Aria), Electron shell in `desktop/`; known gaps in review/m4/findings.md |
| M5 | Evaluation, visual review, packaging | Gold set + harness with metrics; Playwright journeys for every user story at desktop/tablet × light/dark; findings logged and high/medium fixed; Docker image + install script; CI; licence audit | Done: eval/ (SBD, motion, content, ASR, search relevance, known-item, throughput, storage bench), review/m4 (builder pass + fresh reviewer pass), Dockerfile, install.sh, CI and release workflows, docs/licences*.md |

## Current status

- Core (`core/metachlorian`, Python 3.10+): `metachlorian serve` runs the API, MCP server, web app and analysis workers.
- Web app (`app/`) and desktop shell (`desktop/`): built, typechecked, linted, unit-tested, journeys captured in `review/m4`.
- Cutawan: imports Metachlorian packages and uses it as a B-roll source (branch in the Cutawan repo).
- Added at the owner's request: hosted model providers (OpenAI key, OpenRouter, ChatGPT via Codex CLI) behind explicit
  consent, and local face identity (name, merge, search and forget people), both with UI, API, MCP and tests.
- Evaluation: every number is in [eval/README.md](eval/README.md); search ranking was revised after blind pooled judgments.

## Next

1. Binary (b1) in-RAM vector codes with int8 rescoring, so 10 M shots fit a 16 GB machine (ADR 002 gate).
2. A multilingual sentence embedder for meaning-level speech search (OPEN_QUESTIONS Q10).
3. Verify the hosted providers against live accounts (not reachable from the build environment) and tune default models.
4. GPU-tier evaluation of VLM captions and shot size (the weakest CPU-tier signal).
5. Publish the SigLIP ONNX release asset (Q4) and sign installers (Q3).
6. Re-run the visual review on real hardware with 10,000+ results (grid scroll and preview latency).

## Known risks

- No GPU in the build environment: VLM throughput figures are CPU-only and pessimistic.
- Hugging Face is unreachable from the build environment, so model weights were obtained from GitHub releases, Google storage
  and Docker Hub OCI artefacts; the SigLIP ONNX export must be published as a release asset (OPEN_QUESTIONS Q4).
- Footage for evaluation is limited to openly licensed clips we could reach; some are local-only (licence unclear).
