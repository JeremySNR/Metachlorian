# Photos and Lightroom Classic

Metachlorian can index photographs in place, help an MCP agent compare a shortlist, and send recoverable edits to Lightroom Classic. Codex or another vision-capable agent makes the photographic decisions. The small Lightroom plug-in is the local connection to Adobe's catalogue and renderer; it does not run another agent.

This is a **source preview**, not included in the published **v0.2.0 installers**. Automated tests exercise the Python service, actual Lua handler with SDK doubles, TCP transport, REST and MCP. Real Lightroom rendering and UI interaction still need the Mac/Windows certification described below. Editing is explicitly limited to Classic **15.6** in this version; other versions can be indexed but are not silently declared compatible.

## Start

1. Build the current source and run Metachlorian on the **same computer and OS account as Lightroom Classic**. Use a desktop build from that checkout or a native Python installation. A NAS/container cannot control desktop Classic through this adapter.
2. Open **Photos → Enable Photos**. Install the photo models when prompted, or keep metadata-only search. Existing video model downloads are reused. New desktop installations can choose Photos without downloading speech/audio models.
3. Select **Install connector files**. In Lightroom, choose **File → Plug-in Manager → Add**, select the displayed `MetachlorianPhotos.lrplugin` directory and enable it. Restart Lightroom if the connector has not started. Its status is available under **Library → Plug-in Extras**.
4. Select **Sync catalogue**, or index a folder. Synchronisation indexes metadata first, then analyses available renditions locally. Existing Smart Previews are used through Lightroom. Metachlorian does not create Smart Previews for the whole catalogue or parse/write `.lrcat` internals.
5. Name people in the photo inspector or People screen. Correct a wrong match with **Not this person**, or merge groups in People. Children, unusual poses and small faces still need human verification.
6. Connect your agent to the running core's `/mcp/` endpoint and ask it to select and edit photographs. Jobs and reviewed copies appear in Photos → Activity. Finished selections appear in Lightroom under the **Metachlorian** collection set and can also be found through Metachlorian Collections.

For a native install on macOS, with Git, Node.js 22+, FFmpeg and uv installed:

```sh
git clone https://github.com/JeremySNR/Metachlorian
cd Metachlorian
cd app && npm ci && npm run build
cd ..
uv venv -p 3.11 core/.venv
uv pip install -p core/.venv/bin/python -e 'core[photos]'
core/.venv/bin/metachlorian models fetch --pack photos
core/.venv/bin/metachlorian serve
```

On Windows, run these steps in PowerShell individually, use `core/.venv/Scripts/python.exe` for the pip target and
`core/.venv/Scripts/metachlorian.exe` for the CLI. Open `http://127.0.0.1:8765` while the server is running.
Linux can index local folders, but Lightroom Classic itself requires macOS or Windows.

JPEG, PNG, TIFF and WebP use Pillow; RAW uses rawpy/LibRaw and HEIC uses the decoder-only pi-heif extra. ExifTool, if available on `PATH`, supplies richer capture metadata. Without ExifTool, Pillow reads supported EXIF; RAW metadata can be sparse until the file is linked to Lightroom. Metadata omissions remain unknown. A JPEG/HEIC HDR source is inspected as SDR, not as an HDR finishing proof.

## Connect Codex

Create an agent token in Settings → Agents with `library:read`, `photos:edit` and `collections:write`. Read-only tokens can search and inspect but cannot edit. The equivalent CLI is:

```sh
metachlorian token codex-photos --scopes library:read,photos:edit,collections:write
```

Put the token in the environment used to launch Codex, for example `METACHLORIAN_TOKEN`, and configure:

```toml
[mcp_servers.metachlorian]
url = "http://127.0.0.1:8765/mcp/"
bearer_token_env_var = "METACHLORIAN_TOKEN"
```

Use the URL displayed in Photos when the desktop core chooses another port. Prefer HTTP over launching a separate stdio core: the running core owns the Lightroom connection and durable queue. The connector uses two loopback sockets, defaults 58773/58774, with a per-message token at `~/.config/metachlorian-lightroom/token`. If you change ports, update both the connector and core configuration and restart the core.

Example request:

> Find 20 favourites from our July holiday featuring my son. Compare similar frames, include quiet moments as well as smiles, and keep some environmental photographs. Edit naturally in Lightroom on virtual copies. Inspect the renders and put the results in “July family favourites”.

The MCP instructions and `metachlorian://photos/editing-guide` resource teach the workflow. Selection and revision stay with the connected agent; there is no claim that a scalar score determines the best photograph.

| Step | Tool | Contract |
| --- | --- | --- |
| Find candidates | `search_photos` | Text/visual retrieval plus person, date, camera, lens, folder, catalogue, rating, collection and availability filters. Expand a burst using `filters.burst_id` and `diverse=false`. |
| Inspect | `get_photo`, `get_photo_previews` | Metadata, face boxes, evidence, uncertainty and **actual JPEG image content**. Up to eight previews per call. Native detail requires a region and accessible original. |
| Read editing context | `get_photo_edit_context` | Exact current develop revision, available controls/units, guidance and recovery snapshots. |
| Establish baseline | `begin_photo_edits` | 1–100 selected photos; expected revisions and idempotency key required. Creates owned virtual copies and fresh baselines. Folder files are imported in place only when selected for editing. |
| Edit and render | `apply_photo_edit` | Validated settings, supported AI masks or Auto operations. Returns a job. Maximum three refinement rounds per session. |
| Review | `get_photo_job`, `get_photo_previews` | Wait for completion, inspect full-frame images and relevant details; settings readback alone is insufficient. |
| Recover | `resume_photo_job`, `restore_photo_edit` | Reconcile a lost response or restore an owned snapshot against a newly read revision. No global Undo. |
| Deliver | `finish_photo_edits` | Supply each visually reviewed revision and a collection name. Freshness is rechecked before adding copies. |

Reuse the **same idempotency key and arguments** when retrying an uncertain request. A `waiting` job can be resumed after reconnecting Lightroom. A `conflict` means a new context/review is necessary. If a connector operation stopped partway through, its receipt prevents replay; context lists the recovery snapshot. Restore explicitly after inspecting the changed copy. Cancellation stops at an operation boundary and retains created copies/snapshots. Partial batch outcomes remain in the job result.

## What it measures and edits

Local measurements include rendered clipping, luminance distribution, scale-qualified gradient/Laplacian sharpness, face and eye-region detail, perceptual hashes, short capture bursts, possible near-horizontal lines and conservative framing suggestions. The shared SigLIP model retrieves image content. YuNet/SFace provide face detection and local matching when enabled. None of these measurements is a calibrated aesthetic, emotional or original-resolution focus judgement.

For portraits/family, preserve expression, gesture, believable skin and the moment. Closed eyes in laughter or sleep can be desirable. For travel, consider context, light, perspective and variety. Aperture, shutter speed and ISO explain capture conditions; they are not ranking rules. A Smart Preview cannot establish native eye focus or RAW highlight recoverability.

The connector intersects the allowlist with settings actually present on each photograph and exposes units/ranges. RAW temperature is Kelvin; JPEG temperature is relative. Operations are validated before writing and read back afterward. Supported families include exposure and tone, white balance, RGB/parametric curves, HSL, colour grading, crop/straightening, perspective, lens controls, sharpening/noise reduction, vignette/grain and simple subject/sky/background masks. Natural sessions reject automatic black-and-white conversion; creative sessions opt in. Profile changes require an installed profile and successful readback.

**Manual/capability-gated in this release:** Point Color, people/part/range/gradient-mask geometry, guided perspective, healing/Generative Remove/reflection removal, Lens Blur, Enhance/Denoise, HDR/panorama merges, HDR output and Assisted Culling internals. The agent gets a manual handoff instead of an unverified success. The guide covers these families, but documentation does not make their APIs writable.

Edits always target an owned virtual copy. The source remains intact. Lightroom snapshots capture the baseline and candidate states, including settings beyond the small write allowlist. The catalogue remains authoritative for full develop/mask data. Applying settings, restoring a snapshot and finishing a collection all check expected revisions; completed receipts cannot hide subsequent human changes.

## Storage and privacy

Originals are referenced, not copied. Offline originals are legitimate records with unknown file size/hash. Catalogue identity + Lightroom photo ID distinguish virtual copies. Folder photos keep their Metachlorian identity when linked to a Lightroom master. RAW/JPEG files remain separate records; there is no automatic content-hash deduplication or cross-catalogue relinking in this release.

The default **256 MiB** cache covers retained JPEG previews and reserved temporary Lightroom exports together. A process lock permits one reserved full-resolution render at a time. Old previews are evicted and abandoned scratch exports removed. Face crops are generated on request. Responses use `Cache-Control: no-store`. A full-resolution export larger than the budget is refused before rendering; request smaller evidence or increase `photo_cache_mib` in the configuration (16–4096).

The persistent index target is **2 GiB for 100,000 photographs**, excluding model weights and Lightroom-owned files. The photo model pack is approximately **947 MB once**, shared with videos. MediaPipe landmarks are optional: install `core[photo-landmarks]` and fetch `face-landmarker` separately. That model has a pinned URL/checksum and its expression coefficients remain explicitly uncalibrated. No new large VLM, aesthetic model, cloud photo store or second copy of embeddings is installed by this feature.

Database size and cache use are exposed in photo status; the database total includes video records. Snapshots, virtual copies and Adobe AI data can grow Lightroom's catalogue/`.lrcat-data`; the Metachlorian cache does not govern Adobe's storage. Search indexes are rebuildable. Expensive analysis checkpoints and yields between photos to interactive edit jobs. Sync is explicit; it does not continuously watch every Lightroom change. A context/preview/write always rechecks the current revision.

Photo analysis runs locally and does not inherit public contribution or remote-captioning paths. **Previews explicitly requested by an MCP agent are sent to that agent**, which may be hosted. Face embeddings are not returned by REST/MCP. Rights restrictions apply to agent preview access, and editing is a separate token scope. Naming and regrouping people requires a human account.

## Evaluation and release gates

Run automated checks with `cd core && .venv/bin/python -m pytest --cov`, and the web checks with `cd app && npm run typecheck && npm run lint && npm test && npm run build`. The Lua contract suite uses Lua 5.1 through the development-only `lupa` dependency.

```sh
core/.venv/bin/python eval/photo_benchmark.py --out /tmp/photo-scale.json scale --count 100000
core/.venv/bin/python eval/photo_benchmark.py --out /tmp/photo-preferences.json preferences judgements.json
```

The scale command creates and deletes a temporary synthetic catalogue with 768-dimensional vectors and three face observations per image. It reports storage and real SQL/ANN retrieval latency with encoder inference excluded. It is not a benchmark of Lightroom or photographic judgement.

The [recorded Linux run](../eval/runs/photos-scale-2026-11-01/report.json) used 650 MiB including the reusable ANN cache at 100,000 photographs. Metadata search p95 was 131 ms; warm hybrid retrieval p95 was 365 ms; reopening the saved index and querying took 527 ms. A completely new ANN build took about 60 seconds. Startup warms the index in the background and subsequent changes update it incrementally. These figures describe this synthetic fixture and machine, not all real catalogues.

For quality comparisons, `judgements.json` is a list of objects with `event_id`, `category` (`portrait`, `travel`, `family`), `blind: true`, `preferred` (`baseline`, `candidate`, `tie`) and `severe_regression`. Use one independently sampled event per comparison, hidden treatment labels, the same output dimensions and a preserved baseline. The promotion gate requires at least 30 judgements per category, a 95% Wilson lower bound over .5 on decisive votes, and no severe regressions. The user's own family/travel preferences take precedence over generic aesthetics. No optional enhancement model is promoted without those measurements.

Before declaring a Lightroom/platform combination supported, record the exact app build, OS/architecture and results for: catalogue paging and restart; offline originals with/without Smart Previews; all eight EXIF orientations; camera RAW/JPEG/HEIC/TIFF/PNG; current crop/rotation/profile; each enabled control and units; subject/sky/background mask completion; native crop fidelity; user intervention; disconnect before/after each operation receipt; full snapshot restore; original hash unchanged; selection/module restoration; collection idempotency; and disk use over repeated 100,000-image browsing/editing. Run on **macOS and Windows** with an expendable test catalogue first. These live checks and blind preference results are outstanding, not inferred from mocks.

## Sources and reused software

The detailed rationale, alternatives and tutorial syllabus are in [the Lightroom research](research/lightroom-classic.md). The guide uses public Adobe/Julianna Kost materials; it does not claim completion of paywalled classes.

| Dependency/reference | Use and licence |
| --- | --- |
| [Automaat/lightroom-mcp](https://github.com/Automaat/lightroom-mcp/tree/afa4b887ec65810263fd3f3fb40e22f7669beae8) | Pinned MIT Lua connector; restricted dispatcher, operation receipts, cache exports and ownership checks added. Full attribution is bundled in `UPSTREAM.md` and `UPSTREAM-LICENSE.txt`. Its TS server is not used. |
| [Adobe Lightroom Classic SDK](https://developer.adobe.com/lightroom-classic) | Supported integration boundary; no direct catalogue writes. |
| [Kost Lightroom training](https://jkost.com/blog/lightroom-training-videos) | Profiles, tone, colour, composition, masks, detail and output guidance. |
| [rawpy](https://github.com/letmaik/rawpy) / LibRaw | MIT wrapper; LibRaw licensing/third-party notices retained in the installed distribution. |
| [pi-heif](https://github.com/bigcat88/pi-heif) | Decoder-only HEIF wrapper, avoiding an unnecessary HEVC encoder distribution. Retain wrapper/libheif notices. |
| OpenCV YuNet/SFace, existing SigLIP and USearch | Reuse existing model registry/licences and compact local indexes. |
| [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker) | Optional Apache-2.0 runtime/model evidence, not emotion labels. |

Noncommercial-only aesthetic weights are not added to the default product. Larger embedding/quality models remain benchmark candidates rather than unmeasured downloads. Desktop bundling retains dependency distribution metadata/licences alongside the connector's MIT licence.
