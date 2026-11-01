# Photos and Lightroom Classic

Metachlorian can index photographs in place, help an MCP agent compare a shortlist, and send recoverable edits to Lightroom Classic. Codex or another vision-capable agent makes the photographic decisions. The small Lightroom plug-in is the local connection to Adobe's catalogue and renderer; it does not run another agent.

This is a **source preview**, not included in the published **v0.2.0 installers**. Automated tests exercise the Python service, actual Lua handler with SDK doubles, TCP transport, REST and MCP. Real Lightroom rendering and UI interaction still need the Mac/Windows certification described below. Global editing is enabled for Classic **14.2–15.6**, with controls checked per photograph. AI subject, sky and background masks remain restricted to **15.6**. This is an adapter compatibility range, not a claim of live platform certification.

## Start

1. Build the current source and run Metachlorian on the **same computer and OS account as Lightroom Classic**. Use a desktop build from that checkout or a native Python installation. A NAS/container cannot control desktop Classic through this adapter.
2. Open **Photos → Enable Photos**. The setup walks through **Choose your photos → Connect Lightroom → Use your agent**. Choose **Lightroom catalogue** if your pictures are already in Lightroom, or **Photo folder** to index a folder in place. Adding files does not establish a Lightroom connection.
3. In **Connect Lightroom**, select **Copy connector files**. In Lightroom, open **File → Plug-in Manager → Add**, select the displayed `MetachlorianPhotos.lrplugin` folder and enable it. Keep that folder in place. If it is already installed, copy the updated files and use **Reload Plug-in**. Select **Start connection** in its panel if needed.
4. Select **Check connection** in Metachlorian. A successful response shows the actual Lightroom version, catalogue and connector version. The Lightroom panel separately shows its last authenticated request and action; **Refresh status** updates it. Copied files alone are never treated as proof of a connection. Errors explain the next step.
5. Select **Sync catalogue**, or finish indexing your folder. Metadata appears first; image understanding follows in **Activity**. Existing Smart Previews are accessed through Lightroom. Metachlorian does not create them for the whole catalogue or parse/write `.lrcat` internals. Open **Library details → Install photo models** for visual search, or keep metadata-only search. Existing video model downloads are reused.
6. Open **Use your agent** for the actual MCP endpoint, Codex configuration, required token scopes and a sample brief. Your agent chooses and edits photographs. The plug-in carries out requests; it does not choose a look by itself. **Prepare virtual copies** creates recoverable copies for an agent to edit; it does not apply the brief automatically.
7. Browse, search and compare in **Library**. Name people in the inspector or People screen; correct a wrong match with **Not this person**. Select photographs and choose **Create edit brief** to describe a look, then **Copy brief for agent**. The copied brief includes the selected photo references. Natural, Warm film and Black & white are starting points for the brief, not one-click presets.
8. Open **Edits** to review a rendered virtual copy alongside its source photograph and save the reviewed revision to a Lightroom collection. **Activity** tracks all jobs. Finished selections appear in Lightroom under the **Metachlorian** collection set and in Metachlorian Collections.

After the first import, Photos opens directly to the gallery. Use **Add photos** for another source and **Setup & agent** to revisit the connection or agent instructions. **Library details** shows analysis coverage, model downloads and storage use. Selecting photographs keeps the gallery visible, with Compare and Create edit brief in the selection bar. The inspector scrolls independently and keeps your chosen information view as you move between photos. The photo search field and Ctrl/Cmd+F search Photos; the toolbar's **Search videos** button opens the video search.

**Already indexed a folder?** You do not need to re-index everything or duplicate your originals. After connecting Lightroom, opening a preview or editing context matches the exact file path to an existing catalogue master. Its current Lightroom settings and rendered preview then become available, including for RAW files without a local decoder. Only selected files not already in the open catalogue are imported in place when an edit begins. If the file is elsewhere or the wrong catalogue is open, reconnect the correct original/catalogue first.

**Connection troubleshooting:** keep both applications open under the same OS account; check that local ports match (defaults **58773 / 58774**); update and reload the connector if prompted. Connection status remains visible above the library; select it to open the connection details. They distinguish a missing token, refused connection, timeout, incompatible connector and missing edit permission. Use **Library details → Refresh analysis** to retry photographs that could not be analysed before connecting. For an interrupted edit, resume its existing job rather than submitting the write again with a new key.

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

Create an agent token in Settings → API tokens for agents with `library:read`, `photos:edit` and `collections:write`. Read-only tokens can search and inspect but cannot edit. The equivalent CLI is:

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
| Verify readiness | `get_photo_workflow_status` | Actively checks the connector, Lightroom version, catalogue, editing permissions, RAW/HEIC decoders and setup state. Fix blockers before selecting or editing. |
| Find candidates | `search_photos` | Text/visual retrieval plus person, date, camera, lens, folder, catalogue, rating, collection and availability filters. Expand a burst using `filters.burst_id` and `diverse=false`. |
| Inspect | `get_photo`, `get_photo_previews` | Metadata, face boxes, evidence, uncertainty and **actual JPEG image content**. Up to eight previews per call. Native detail requires a region and accessible original. |
| Read editing context | `get_photo_edit_context` | Exact current develop revision, available controls/units, guidance and recovery snapshots. |
| Establish baseline | `begin_photo_edits` | 1–100 selected photos; expected revisions and idempotency key required. Creates owned virtual copies and fresh baselines. Existing catalogue masters are matched by path; other folder files are imported in place only when selected for editing. |
| Edit and render | `apply_photo_edit` | Validated settings, supported AI masks or Auto operations. Returns a job. Maximum three refinement rounds per session. |
| Review | `get_photo_job`, `get_photo_previews` | Wait for completion, inspect full-frame images and relevant details; settings readback alone is insufficient. |
| Recover | `resume_photo_job`, `restore_photo_edit` | Reconcile a lost response or restore an owned snapshot against a newly read revision. No global Undo. |
| Deliver | `finish_photo_edits` | Supply each visually reviewed revision and a collection name. Freshness is rechecked before adding copies. |

The agent should report the chosen filename, edited virtual copy/session, actual changes, rendered review and any unverified fine detail. If it falls back to manual Lightroom interaction, it must say so; search results alone are not visual selection or proof of an edit.

Reuse the **same idempotency key and arguments** when retrying an uncertain request. A `waiting` job can be resumed after reconnecting Lightroom. A `conflict` means a new context/review is necessary. If a connector operation stopped partway through, its receipt prevents replay; context lists the recovery snapshot. Restore explicitly after inspecting the changed copy. Cancellation stops at an operation boundary and retains created copies/snapshots. Partial batch outcomes remain in the job result.

## What runs automatically versus what the agent judges

The photo inspector has Overview, Analysis, People and Metadata views. Its content scrolls independently of the library, with previous/next and close controls kept visible. Analysis shows the resolution and source of the measured rendition, near-white/near-black pixels, detail energy, face/eye-region measurements, framing hints and the models actually used for that analysis. Missing models and unavailable previews are not presented as successful visual understanding.

Photos currently has a narrower pipeline than video: no automatic VLM scene caption, OCR, structured photographic critique, colour-harmony/skin-tone assessment or learned aesthetic ranking is generated during indexing. Video has separate captioning, visual tags, OCR, place, motion, speech/audio and fusion stages, depending on configuration. Photo expression, composition and editing decisions rely on the connected vision-capable agent inspecting previews. SigLIP embeddings supply retrieval, not a written understanding of every photograph.

A future richer photo analysis should cache compact descriptions and critiques against the image/develop revision and model version, reuse the existing configured vision provider, and make remote analysis opt-in. That would add textual evidence without duplicating originals. It is not implemented by the inspector improvements.

## What it measures and edits

Local measurements include rendered clipping, luminance distribution, scale-qualified gradient/Laplacian sharpness, face and eye-region detail, perceptual hashes, short capture bursts, possible near-horizontal lines and conservative framing suggestions. The shared SigLIP model retrieves image content. YuNet/SFace provide face detection and local matching when enabled. None of these measurements is a calibrated aesthetic, emotional or original-resolution focus judgement.

For portraits/family, preserve expression, gesture, believable skin and the moment. Closed eyes in laughter or sleep can be desirable. For travel, consider context, light, perspective and variety. Aperture, shutter speed and ISO explain capture conditions; they are not ranking rules. A Smart Preview cannot establish native eye focus or RAW highlight recoverability.

The connector intersects the allowlist with settings actually present on each photograph and exposes units/ranges. RAW temperature is Kelvin; JPEG temperature is relative. Operations are validated before writing and read back afterward. Supported families include exposure and tone, white balance, RGB/parametric curves, HSL, colour grading, crop/straightening, perspective, lens controls, sharpening/noise reduction, vignette/grain and, on 15.6, simple subject/sky/background masks. Natural sessions reject automatic black-and-white conversion; creative sessions opt in. Profile changes require an installed profile and successful readback.

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
