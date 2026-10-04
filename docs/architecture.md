# Architecture

See [decision 001](decisions/001-architecture-and-delivery.md) for why it is shaped this way.

## Components

| Component | Where | What it does |
|---|---|---|
| Core | `core/metachlorian` (Python) | Ingest, analysis workers, storage, search, REST API, MCP server, exports. Runs as `metachlorian serve` |
| Web app | `app/` (React 19 + TypeScript + Vite) | The UI. Built to `app/dist` and served by the core at `/` |
| Desktop shell | `desktop/` (Electron) | Wraps the web app; solo mode starts a local core, team mode connects to a shared one; native drag-out and Cutawan hand-off |
| Cutawan integration | Cutawan repo, `--import-package` | Opens Metachlorian packages as rough cuts |

Agents always talk to the core, never to the UI, so agent access does not depend on anyone having the app open.

## Data model

* **Asset**: one source file (content-hashed; duplicates at other paths are recorded, not re-processed).
* **Shot**: a run of frames between two boundaries, or a segment of a long take. Uid = asset uid + start frame, stable
  across re-runs.
* **Moment**: a point or span inside a shot (speech utterance with word timings, on-screen text, face presence, sound event).
* **Signal**: one row per (target, name, analyser): value (JSON), confidence, model version. Replaced only by the analyser
  that produced it.
* **Correction**: stored separately with the person/agent, time, note and an anchor (shot uid + time span) so it re-attaches
  after re-segmentation. Corrections always win when records are built.
* **Rights**: per asset, overridable per shot: status, permitted uses, channels, territories (ISO 3166), dates, releases,
  brand safety, attribution, notes.

The *effective record* of a shot is built from signals with precedence human > fusion > best analyser, then indexed into
typed filter columns (`shot_index`), faceted terms (`shot_terms`), full text (`shot_fts`, FTS5) and vectors (`vectors` table,
mirrored into an in-memory usearch HNSW index plus an int8 matrix for exact scoring of filtered candidates).

## Analysis pipeline

Each analyser is a versioned module declaring its dependencies, configuration and resource class. Its *input key* hashes the
file content, its name, version, configuration, model availability and its dependencies' keys. The planner enqueues an
analyser only when no finished run has that key, so:

* unchanged files are never re-processed;
* upgrading one analyser re-runs it and its dependants only;
* configuring a VLM later runs captioning (and fusion/rollup) on the existing library without touching anything else.

Jobs live in the library database with leases and heartbeats (crashed workers' jobs are retried), priorities (new uploads
and the fast lane first: proxy, shots, keyframes, embeddings), and atomic commits of output + job completion.

| Analyser | Deterministic? | Output |
|---|---|---|
| technical | yes | ffprobe/exiftool metadata: resolution, fps, codec, bit depth, colour transfer (HDR), camera, lens, capture date, GPS |
| proxy | yes | 540p H.264 proxy with 1 s GOP, 16 kHz audio, sprite sheets, poster |
| shots | yes | cuts, dissolves, fades, long-take segments, visual change rate |
| keyframes | yes | up to 5 keyframes per shot, sharpest poster |
| embed | model | SigLIP image embeddings per keyframe and shot |
| visual_tags | model | zero-shot vocabulary labels with calibrated confidence (CPU tier) |
| motion | yes | camera movement, stability, motion energy (KLT + RANSAC similarity, parallax residual) |
| quality | yes | sharpness, exposure, noise, blockiness, colour, letterbox, log/flat likeness, saliency |
| audio | yes + model | EBU R128 loudness, energy, silence; AudioSet events (CED-mini) → audio classes |
| speech | model | Silero VAD, Parakeet TDT transcript with word timings, Whisper language ID, diarisation |
| ocr | model | text, titles, lower thirds, burned-in captions |
| people | model | person and face counts, sizes, positions (no identity), COCO objects |
| caption | model (optional) | VLM caption and labels constrained to the vocabularies, validated and retried |
| fusion | rules + optional LLM | resolved record: shot size, angle, setting, time of day, role, pace, mood, uses, usability, 9:16 crop |
| rollup | rules + optional LLM | asset structure, pace, raw/selects/finished, summary |

## Search

1. Parse the query (rules + vocabularies): hard filters (duration, resolution, fps, orientation, log, HDR, people, speech),
   vocabulary preferences (soft unless `strict`), negations, places, rights intent, result count, the "line to cover" for B-roll.
2. Choose a plan by filter selectivity: ≤ 20k candidates → exact scoring over candidates; otherwise retrieve pools
   (ANN, FTS5/BM25 with IDF pruning, top term matches) and apply filters to the pool.
3. Fuse with weighted reciprocal rank fusion, add small priors (people preference, quality), apply the rights check for the
   intended use, page with cursors, compute facets, and explain every result.

## Security

Roles viewer/editor/admin/agent with scopes; argon2 passwords; hashed bearer tokens; session cookies with a custom-header
CSRF rule; solo mode accepts only loopback clients with a loopback Host header (DNS-rebinding defence); refusal to listen on a
network address without auth; audit log of all writes and all agent calls; hosted model adapters off by default and refused
unless `allow_remote` is set, with the egress state shown in the UI.

Community sharing is independent of model providers. New downloads of explicitly public YouTube videos enroll in a
durable local outbox while `community_enabled` is true (the default). The publisher waits for analysis to finish,
checks that the downloaded bytes have not been replaced, verifies public visibility without cookies, and sends only
allowlisted machine signals and timestamped speech/OCR moments. Local imports and duplicate local assets never enroll.
Opt-out suppresses outstanding contributions without backfilling on re-enable. Egress reporting shows the community
destination separately from hosted model providers. Private library search never sends its records to community search.
The separate [community service](https://github.com/JeremySNR/Metachlorian-community) uses its own Postgres database,
verifies public status independently with YouTube Data API, deduplicates contributions and indexes content by timestamp.
