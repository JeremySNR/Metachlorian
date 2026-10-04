# 012. Timeline interchange formats and the Cutawan handoff

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context

Selected shots have to leave Metachlorian in a form that editing tools open
without manual relinking:

1. **NLEs** (DaVinci Resolve, Premiere Pro, Final Cut Pro, Avid Media
   Composer) need a timeline: a selects stringout or a rough cut with
   in/out points, tracks and markers that point at media.
2. **Cutawan** (sister project, MIT, Electron + React) turns a long video
   into captioned vertical clips. An agent should be able to go from "find
   footage for this brief" in Metachlorian to "rough cut open in Cutawan"
   with no human copying files.

The concrete contract (package layout, manifest, Cutawan changes) is in
[docs/integration/cutawan-contract.md](../integration/cutawan-contract.md),
and the manifest schema is in
[cutawan-package.schema.json](../integration/cutawan-package.schema.json).
This ADR records the format choices and the integration approach.

### Format landscape (October 2026)

| Format | What it carries | Who reads it | Tooling / licence | Sources |
|---|---|---|---|---|
| **OpenTimelineIO** (`.otio` JSON; `.otioz` zip bundle / `.otiod` directory bundle with `content.otio` + flat `media/`) | Multi-track timelines, clips with source ranges, gaps, transitions, linear speed, markers, arbitrary per-object `metadata` | **Resolve ≥18.5** (import/export .otio and .otioz). **Premiere Pro ≥26.0** (Jan 2026, import/export). **Avid MC ≥2025.6** (import). FCP has no native support | `OpenTimelineIO` 0.18.1 (2025-11-09), **Apache-2.0**, wheels for CPython 3.9–3.13. Since 0.16 non-native adapters live in separate packages or the `OpenTimelineIO-Plugins` meta-package (AAF, ALE, burnins, cmx_3600, fcp_xml, fcpx_xml, hls, maya, svg, xges) | [repo](https://github.com/AcademySoftwareFoundation/OpenTimelineIO), [PyPI](https://pypi.org/project/OpenTimelineIO/), [plugins](https://pypi.org/project/OpenTimelineIO-Plugins/), [bundles](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/docs/tutorials/otio-filebundles.md), [Resolve 18.5](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_18.5_New_Features_Guide.pdf?_v=1681801210000), [Premiere release notes](https://helpx.adobe.com/premiere/desktop/whats-new/release-notes.html), [Avid 2025.6](https://www.avid.com/resource-center/whats-new-avid-media-composer-20256) |
| **FCPXML** (`.fcpxml`; `.fcpxmld` bundle since 1.10) | Rational-time timelines (`1001/30000s`), assets/formats as resources, spine/lanes, keywords, markers, roles, `<metadata>` | **Final Cut Pro**: 10.6 → 1.10, FCP 11 → 1.13 (can still write 1.11/1.12), **FCP 12.0 (Jan 2026) → 1.14**. **Resolve** imports 1.10 from v18 (≤1.9 in v17) | Apple DTD per version. `otio-fcpx-xml-adapter` 1.0.0 (Jul 2023, Apache-2.0) supports tracks, audio, gaps, markers and nesting but **not transitions, effects or speed**, and is tested only up to Python 3.10 | [FCP release notes](https://support.apple.com/en-us/102825), [Apple XML guide](https://support.apple.com/guide/final-cut-pro/use-xml-to-transfer-projects-verdbd66ae/mac), [fcpxmld](https://www.intelligentassistance.com/fcpxml-bundles-with-a-fcpxmld-extension/), [Resolve forum on 1.9/1.10](https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=151297), [adapter](https://pypi.org/project/otio-fcpx-xml-adapter/) |
| **CMX 3600 EDL** (`.edl`) | One video track (plus audio channels), cuts, dissolves/wipes, reel names, timecode, `* FROM CLIP NAME:` comments | Every NLE, conform and grading tool | `otio-cmx3600-adapter` (Apache-2.0). Single video track, transitions, linear speed, CDL; Avid, Premiere and Nucoda styles | [Wikipedia](https://en.wikipedia.org/wiki/Edit_decision_list), [adapter](https://github.com/OpenTimelineIO/otio-cmx3600-adapter), [limits](https://cutconvert.com/guides/what-is-an-edl) |
| **FCP7 XML / xmeml** (`.xml`) | Multi-track sequences, clips, markers, basic effects | Premiere (all versions), Resolve, many tools | `otio-fcp-adapter` (Apache-2.0). Tracks, audio, gaps, markers, nesting. No transitions, effects or speed | [adapter](https://github.com/OpenTimelineIO/otio-fcp-adapter) |
| **AAF** (`.aaf`) | Rich (Avid bins, audio mix, effects), complex | Avid MC, Pro Tools, Resolve, Premiere | `otio-aaf-adapter` (Apache-2.0) over `pyaaf2` (**MIT**, pure Python) | [adapter](https://github.com/OpenTimelineIO/otio-aaf-adapter), [pyaaf2](https://github.com/markreidvfx/pyaaf2) |
| Resolve project (`.drp`) / scripting API | Everything, Resolve-only | Resolve | Proprietary, Studio-gated scripting | — |

The cross-format pattern is clear: OTIO is the open hub with first-party
import in Resolve, Premiere and Avid. FCPXML is needed only for Final Cut Pro.
EDL is the universal fallback.

### What Cutawan accepts today (read from `/home/user/cutawan`)

* **One source video per project.** `Project.video: VideoInfo` (path, fps,
  size). `createProject(path)` and `createProjectFromUrl(url)` probe it and
  write `userData/projects/<id>/project.json`
  (`src/main/pipeline/index.ts`, `src/main/projects.ts`). There is no
  multi-source timeline.
* **Transcript reuse.** `ensureTranscript` skips transcription when
  `project.transcript` is already set (`src/main/pipeline/projectTranscript.ts`).
  A package that brings a word-timed transcript saves the transcription cost.
* **B-roll is still images only.** `BrollItem {trigger, query, start, end
  (absolute source s), mode: fullscreen|overlay, imagePath, sourceUrl,
  enabled}` (`src/shared/types.ts`). `attachBroll` asks the LLM for spoken
  triggers, then `searchImage` queries Wikipedia, then Openverse, without
  keys (`src/main/pipeline/broll.ts`, `imagesearch.ts`). Render loops the
  image with `-loop 1 -t … -i image` and overlays it with fades between
  start and end (`src/main/pipeline/render.ts` ~L464–535). The preview shows
  an `<img>` (`PreviewPlayer.tsx` `BrollOverlay`). The README itself warns
  that these web images carry their own licences.
* **No automation entry point.** Everything goes through renderer IPC
  (`src/main/ipc.ts`). There is no CLI argument handling, single-instance
  forwarding, protocol handler or watch folder (only `CUTAWAN_*` test env
  hooks in `src/main/index.ts`). The `media://` allowlist covers
  `userData/projects/**` plus registered source paths
  (`src/main/mediaAccess.ts`).
* MIT licence, which is compatible with Metachlorian's Apache-2.0. The two
  share only a file format, not code.

## Options considered

### Interchange formats

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **OTIO (.otio) as canonical model + exporter hub** | Lossless for our needs (tracks, ranges, markers, metadata). Native import in Resolve, Premiere 26+ and Avid 2025.6+ | Apache-2.0 | none | ms per timeline | ASWF project, Development Status 4 (Beta) on PyPI but widely deployed | Active (0.18.1, Nov 2025) |
| **FCPXML 1.10 writer** | Required for FCP. Also imported by Resolve ≥18. Rational time avoids drift | Apple DTD (free) | none | ms | Stable since 2021, currently 1.14 | Adapter stale (2023). Own writer is small |
| **CMX 3600 EDL** | Lowest common denominator: one video track, 8-char reels, 999 events, no metadata | Apache-2.0 adapter | none | ms | Decades | Adapter maintained under OTIO org |
| FCP7 XML (xmeml) | Multi-track and markers for Premiere <26 and legacy tools | Apache-2.0 adapter | none | ms | Legacy but universal | Maintained adapter |
| AAF | Best for Avid/Pro Tools audio handoff. Complex, with a history of round-trip bugs | Apache-2.0 + MIT | none | ms | Mature format, fragile interop | Adapter maintained |
| .otioz / .otiod bundles | One file with media, which Resolve opens directly. Requires unique media basenames and **duplicates** media if we also ship `media/` | Apache-2.0 | disk | Copy-bound | Supported since OTIO 0.15 / Resolve 18.5 | — |

### Cutawan integration

| Option | Effort in Cutawan | Agent-driven? | Fit with Cutawan model | Risk |
|---|---|---|---|---|
| I0. Agent renders a stringout MP4, and a human imports it in Cutawan | none | No (a human picks the file) | OK, but transcription is paid again | — |
| **I1. "Import Metachlorian package" + CLI/second-instance entry** | Small: ~1 new main module, 1 IPC handler, argv handling, 2 type fields | **Yes**: `cutawan --import-package <dir>` | Uses the existing single-source model: package stringout = project video, package transcript = project transcript | Low |
| **I2. Video B-roll inserts** (`BrollItem.kind = 'video'`) | Small/medium: render input for video, preview `<video>` | Yes (inside I1) | Natural: A-roll = project video, B-roll = timed inserts, which is exactly Cutawan's overlay model | Medium (tighten remap inside inserts) |
| **I3. Metachlorian as a B-roll provider** (replaces or augments Wikipedia/Openverse) | Medium: provider setting + REST client + rights filter | Yes | Same LLM trigger step, better source (owned, rights-checked video) | Low. Needs a token in settings |
| I4. Multi-source timeline in Cutawan (import OTIO directly) | Large: a new project model and multi-input render | Yes | Re-architecture | High |

## Evidence

* Format support facts as cited in the table above (vendor notes and
  adapter pages, read 2026-10-04).
* The Cutawan facts come from reading its source (paths above). The
  single-source `Project`, transcript reuse and still-image-only B-roll
  shape the contract more than any other factor.
* The manifest schema validates as JSON Schema 2020-12 (checked with
  `jsonschema` 4.26). A full example manifest (A-roll interview + B-roll
  insert) validates with 0 errors. Path traversal (`../`), absolute paths
  and a major version 2 are rejected by the schema.

## Decision

### 1. Interchange

* **Canonical in-memory and on-disk timeline: OTIO.** `build_package`
  builds an `otio.schema.Timeline` from the selection, and every export
  format derives from it. Our tags, shot ids and rights refs go into
  `metadata["metachlorian"]` on clips, where OTIO round-trips them.
* **Ship three formats by default:** `.otio` (Resolve, Premiere 26+, Avid),
  **FCPXML 1.10** (FCP 10.6+ and Resolve 18+; selectable 1.9 for Resolve 17
  and ≥1.11 when needed) and **CMX 3600 EDL** (V1 only, one EDL per video
  track, `FROM CLIP NAME` comments, reel names derived from asset reel or
  ≤8-char hash). Dependencies: `OpenTimelineIO` (core) and
  `otio-cmx3600-adapter`, pinned.
* **FCPXML is written by our own small writer from the OTIO model**
  (asset-clips on a spine, connected clips for B-roll lanes, markers,
  keywords from tags, rational times at sequence rate). It is validated in
  CI against Apple's DTD for the target version. Reason: the upstream
  adapter is stale and drops speed and transitions. It is kept as a test
  oracle for basic structure.
* **Opt-in:** FCP7 XML/xmeml via `otio-fcp-adapter` (Premiere < 26). AAF via
  `otio-aaf-adapter` + `pyaaf2` later, once Avid/Pro Tools users ask, with
  round-trip tests first. `.otioz` on request (it duplicates media).
* Media references in timelines are **relative** (`media/<file>`), with
  unique flat basenames, so the package directory can be zipped into an
  OTIO bundle unchanged. A conform script can also rewrite them to the
  original absolute paths when the NLE runs next to the library
  (`media_policy: none`).

### 2. Cutawan handoff

* **One package format for every consumer** (layout and manifest in the
  contract doc): `manifest.json` (schema `1.x`), `media/` (trimmed proxies
  or originals with handles, plus an optional conformed stringout),
  `transcripts/` (Cutawan's own `Transcript` JSON shape),
  `timelines/` (otio, fcpxml, edl), `thumbs/`, `RIGHTS.md` and `checksums`.
* **Cutawan gets I1 + I2 now and I3 next.** I4 is rejected.
  * I1: a new `importHandoffPackage(dir)` in Cutawan main creates a normal
    project from the package. It supports three modes from
    `manifest.cutawan.mode`: `stringout`, `a_roll_with_inserts`, and
    `broll_library` (no project; feeds the B-roll picker). Entry points are
    the `--import-package <dir>` argv (with `app.requestSingleInstanceLock()`
    forwarding on `second-instance`), plus a "Import Metachlorian package…"
    menu item.
  * I2: `BrollItem.kind?: 'image' | 'video'` and `mediaIn?: number`. Render
    uses `-ss/-t -i` for video inserts instead of `-loop 1`, and the
    preview uses `<video>`.
  * I3: Settings → B-roll source: *Web images (current)* or *Metachlorian
    library* (URL + token, encrypted like the API key). `attachBroll` keeps
    its LLM trigger step and calls Metachlorian REST `search_shots`
    (with `rights` set to the export channel) and `export_clip`
    (proxy, 9:16 safe crop) instead of Wikipedia/Openverse.
* **Rights are enforced in Metachlorian** before media leaves it
  (`check_rights` inside `build_package`). Cutawan shows the package's rights
  summary and credits and warns if the verdict is not `allowed`. It does
  not re-judge rights.
* **Agents drive Metachlorian over MCP and Cutawan over its CLI.** Cutawan
  talks to Metachlorian over REST because it is an app, not an LLM host.
  Both protocols use the same service layer ([ADR 011](011-mcp-interface.md)).

## Consequences

* **Easier**: one build path (OTIO) serves four NLEs and Cutawan. Packages
  are self-describing, verifiable (checksums) and reproducible
  (`idempotency_key`, vocab versions, rights snapshot hash). Cutawan keeps
  its single-source architecture, and its captions, tighten, zoom and
  reframe work unchanged on the stringout.
* **Harder**: we maintain an FCPXML writer and DTD tests. Stringout
  rendering needs a conform step (mixed frame rates and resolutions are
  conformed to the sequence rate; VFR phone footage needs CFR conversion).
  Cutawan must handle tighten-cut remapping across video inserts. Packages
  with trimmed originals can be large, so the default for Cutawan is H.264
  proxies at the target resolution.
* Cutawan has no headless export today. The automated path ends with the
  rough cut *open* in Cutawan. One click exports the MP4. A future
  `--export` flag can close that gap.

## Revisit when

* FCP gains native OTIO, or Resolve or Premiere drop FCPXML/xmeml paths.
* `otio-fcpx-xml-adapter` gets a maintained release covering speed and
  transitions. Then drop our writer.
* OTIO reaches 1.0 or changes its bundle format.
* Cutawan adopts a multi-source timeline (I4). Then let Cutawan import
  `.otio` directly and keep the stringout path only for simple cases.
* Avid or Pro Tools users need audio-stem handoff. Then implement AAF with
  round-trip tests.
