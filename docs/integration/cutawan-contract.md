# Metachlorian → Cutawan handoff contract (package format v1)

Status: proposed (see [ADR 012](../decisions/012-interchange-and-cutawan-handoff.md)).
Schema: [cutawan-package.schema.json](cutawan-package.schema.json) (JSON Schema 2020-12).
Vocabulary ids: [ADR 010](../decisions/010-controlled-vocabularies.md) / `core/metachlorian/vocab/v1`.
MCP tools: [ADR 011](../decisions/011-mcp-interface.md).

## 1. Goal and flow

An agent turns a brief into a rough cut that is open in Cutawan, and no
human moves files:

```
agent ──MCP──▶ Metachlorian                                  Cutawan (desktop)
  1 search_shots(brief, filters, rights={channels, territories})
  2 get_shot / find_similar (refine, pick in/out)
  3 check_rights(shot_ids, intended)        (build_package repeats it)
  4 build_package(items, sequence, target={consumer:"cutawan", aspect:"9:16"},
                  media:"stringout", timelines:[otio,fcpxml,edl])
       └─▶ package dir on shared disk  ─or─  signed zip URL → agent unzips
  5 agent runs:  cutawan --import-package "/path/to/package"
                                   └─▶ validate → copy into userData/projects/<id>/
                                       → project with video, transcript, clips, B-roll inserts
                                       → (optional) caption-whole-video pass, offline
                                       → editor opens on the rough cut
  6 human (or a future --export flag) exports MP4
```

The same package opens in an NLE through `timelines/*.otio|.fcpxml|.edl`.

## 2. Package layout

A directory (or a `.zip` of it with the same structure) named
`<slug>-<package_id>`:

```
manifest.json                  REQUIRED. Validates against cutawan-package.schema.json
RIGHTS.md                      human-readable rights summary + credits (generated)
checksums.sha256               sha256 of every file except itself and manifest.json
media/                         FLAT, unique basenames (OTIO bundle-compatible)
  stringout_a_roll.mp4         optional conformed stringout (Cutawan's project video)
  it_02.mp4                    per-item trims with handles (proxy or original codec)
transcripts/
  stringout_a_roll.json        Cutawan Transcript shape, times on the stringout clock
thumbs/
  it_01.jpg …
timelines/
  seq_main.otio                OTIO, relative media refs → ../media/…
  seq_main.fcpxml              FCPXML 1.10 (default)
  seq_main.edl                 CMX 3600, V1 only (one EDL per video track)
```

Rules:

* All paths in the manifest are relative POSIX paths inside the package. No
  `..`, no absolute paths, no backslashes; the schema enforces this.
  Consumers must also resolve each path and check that it stays inside the
  package root.
* Media basenames in `media/` are unique, so `content.otio` + `media/`
  can be re-bundled as `.otioz` without renaming.
* Writers create the package in a temporary directory and rename it into
  place atomically. `manifest.json` is written last, so a directory that
  has one is complete.
* Packages are immutable. A rebuild with a new selection gets a new
  `package_id`. A rebuild with the same `idempotency_key` returns the
  existing package.

## 3. Manifest essentials

Full definitions are in the schema. Summary:

| Field | Purpose |
|---|---|
| `schema_version` (`1.y.z`), `kind: "metachlorian.package"` | Consumers **reject unknown majors**. Minor versions only add optional fields. Unknown fields may appear only under `extensions` |
| `package_id` (ULID/UUID), `name`, `created_at`, `generator{name, version, instance}` | Identity and provenance |
| `brief{text, requested_by, agent, search}` | What was asked, by whom, through which OAuth client. The echoed search parse makes the selection reproducible |
| `target{consumer, aspect, duration_sec, usage[], channels[], territories[]}` | Intended use. Rights were checked against this |
| `vocab_versions{}` | Vocabulary versions behind every `tags` value |
| `media_policy` | `none` \| `proxies` \| `trimmed_originals` \| `stringout` |
| `assets[]` | Source assets: id, name, duration, `rate` (rational string), size, `start_timecode`, `reel`, `edit_type`, `source_type`, colour state, optional `original_uri` (informative, may be withheld) |
| `media[]` | Every shipped file: `kind` (proxy, trimmed_original, stringout, still, audio, thumbnail), `asset_offset` (asset time at file frame 0), duration, rate, codecs, loudness, crop applied, sha256 |
| `items[]` (shot list) | `item_id`, `shot_id`, `asset_id`, `role` (shot_role), `source_range{in,out}` on the **asset clock**, `handles_sec`, `media{file,in,out}` on the **media clock**, description, `tags{vocab:[ids]}`, quality flags, `transcript_excerpt` (words on asset clock), `safe_crops{"9:16":{rect,track}}`, `rights_ref` |
| `sequences[]` | Rough cut(s): rate, size, tracks (`video`/`audio`, role `a_roll`/`b_roll`/`music`/`voice_over`), clips `{item_id, record_in, duration, source_in?, speed?, transition_in?}`, markers |
| `stringout{sequence_id, file, scope: all\|a_roll, transcript, map[{item_id,in,out}]}` | Single-file conform for single-source consumers |
| `transcripts[]` | `format: cutawan.transcript/1 \| webvtt \| srt`, `language` (BCP 47), `time_base: media\|asset` |
| `timelines[]` | `format: otio \| otioz \| fcpxml \| edl_cmx3600 \| xmeml \| aaf`, version, file, `media_paths: relative\|absolute\|missing` |
| `rights{verdict, intended, counts, checked_at, rights_snapshot_hash, credits[], earliest_expiry, overrides[], records{ref: {verdict, reasons[], model_release, property_release, clearance_flags[], licence, permitted, prohibited, requirements[], credit, valid_from, expires_at}}, human_readable}` | Rights as decided by `check_rights` at build time |
| `cutawan{mode, project_name, flow, video_type, aspect, captions, auto_zoom, follow_speaker, inserts[], prompt}` | How Cutawan should open the package |

### Time model

* Every range is half-open `[in, out)`.
* There are three clocks:
  * **asset** (seconds from the first frame of the original file)
  * **media** (seconds in a shipped file; asset time = media time + `asset_offset`)
  * **sequence/stringout** (seconds from the start of the edit)
* `Time` objects carry authoritative `seconds` and, optionally, `rate`
  (`"30000/1001"`), `frames` and `timecode`, which must agree with
  `seconds`. NLE exports use frames at the sequence rate. FCPXML uses
  rational seconds (`frames*den/num s`). Cutawan uses seconds.
* Stringouts are conformed to the sequence rate (CFR), H.264 High 4:2:0 +
  AAC 48 kHz, keyframe ≤1 s, with loudness recorded rather than normalised.
  Cutawan normalises to -14 LUFS at export.

### Transcript format `cutawan.transcript/1`

This is Cutawan's own `Transcript` type (`src/shared/types.ts`), so Cutawan
can assign it directly:

```json
{ "language": "en-GB", "durationSec": 24.0,
  "segments": [ { "id": 0, "text": "Remote work was never about the tools.", "start": 0.2, "end": 2.6,
                  "words": [ { "text": "Remote", "start": 0.2, "end": 0.5 } ] } ],
  "speech": [ { "start": 0.1, "end": 23.8 } ] }
```

Times are on the clock named by `time_base` (stringout transcripts use
`media`). Word-level timestamps are required, because Cutawan's captions
and tighten-cuts depend on them. `speech` (VAD regions) is optional, and
Cutawan computes it if it is missing.

## 4. How Cutawan ingests a package

### 4.1 Modes (`manifest.cutawan.mode`)

| Mode | Cutawan project video | Transcript | Clips | B-roll |
|---|---|---|---|---|
| `stringout` | `stringout.file` (scope `all`) | stringout transcript | `flow: clips` gives one `Clip` per `stringout.map` entry (`origin: 'package'`, title = item description, no virality score). `flow: whole-video` gives one whole-video clip | none (B-roll is already in the picture) |
| `a_roll_with_inserts` (**default for social rough cuts**) | stringout with `scope: a_roll` (interview/PTC only) | A-roll transcript | whole-video clip (or per-item clips) | each `cutawan.inserts[]` entry → `BrollItem{kind:'video', imagePath: media/<item>.mp4, mediaIn: item.media.in, start, end (stringout s), mode, trigger, sourceUrl: item.web_url}` |
| `broll_library` | none (no project is created) | — | — | items are offered as candidates in the B-roll panel of an open project, and the user or LLM trigger step places them |

Mapping onto Cutawan types (`src/shared/types.ts`):

| Package | Cutawan |
|---|---|
| `cutawan.project_name` \|\| `name` | `Project.name` |
| stringout media file (copied to `projects/<id>/source.mp4`, like URL imports) | `Project.video` via `probeVideo` |
| stringout transcript | `Project.transcript` (so `ensureTranscript` skips transcription) |
| `cutawan.video_type` | `Project.videoType` |
| `cutawan.flow` | `Project.mode` (`clips` / `whole-video`) |
| `cutawan.aspect`, `auto_zoom`, `captions` | `ClipEditState.aspect`, `autoZoom`, `captionsEnabled` (whole-video edits use `wholeVideoEdit(...)`) |
| `items[].safe_crops["9:16"].track` | optional seed for `Clip.focusTrack` (`{t, x, cut}` is the same shape as `FocusKeyframe`), which saves on-device ASD |
| `rights.*`, `package_id`, `generator.instance` | new `Project.handoff` (shown as a banner and in export notes) |

After import, if `flow == 'whole-video'`, Cutawan can run its existing
`captionWholeVideo(project, {aspect, followSpeaker, autoZoom})`. With the
transcript already present this **makes no API calls**, so the import is
fully offline.

### 4.2 Entry points (automation without a human moving files)

1. **CLI**: `cutawan --import-package "<dir-or-zip>"`. On launch, main
   parses `process.argv`. With `app.requestSingleInstanceLock()`, a second
   launch forwards its argv through the `second-instance` event to the
   running app, which imports and focuses the new project. The exit code
   and stdout JSON (`{project_id}` or `{error}`) can be added for agents
   later.
2. **Menu / drag-and-drop**: "Import Metachlorian package…" (`dialog:selectPackage`)
   for humans.
3. *(Phase 2)* `cutawan://import?url=<signed https zip>` protocol handler for
   remote Metachlorian instances. It only accepts hosts in a configured
   allowlist and always asks the user to confirm, because any web page can
   fire a protocol URL.

### 4.3 Validation on import (Cutawan side)

* `schema_version` major must be 1. `kind` must be `metachlorian.package`.
* Every referenced path must exist and resolve inside the package root
  (guards against traversal and symlink escapes). `sha256` is checked when
  present.
* There must be at least one media file Cutawan can probe. For
  `a_roll_with_inserts`, every insert must reference an item with
  `media.file`, and `start < end ≤ video duration`.
* `rights.verdict != allowed`: import, but show a persistent warning with
  the reasons. Cutawan does not override Metachlorian's decision and
  does not hide it.
* Errors are human-readable and name the field (Cutawan style), and nothing
  is written until validation passes. Import is atomic: copy into a temp
  project directory, then rename.

## 5. Minimal Cutawan changes

These are listed in order of value. Phases A and B deliver the end-to-end
agent flow.

**Phase A: package import (I1)**

| File | Change |
|---|---|
| `src/shared/types.ts` | `ClipOrigin` adds `'package'`. `Project` adds optional `handoff?: { packageId: string; schemaVersion: string; instance?: string; rights: { verdict: string; credits: string[]; earliestExpiry?: string; reasons?: string[] } }` |
| `src/main/handoff.ts` *(new, ~250 lines)* | `importHandoffPackage(pathOrZip)`: unzip if needed, validate (hand-written checks in the style of `packageValidation.ts`, no new dependency), copy the stringout to `projects/<id>/source.mp4` and inserts to `projects/<id>/broll/`, `probeVideo`, map the transcript, build clips and B-roll, `saveProject`, `allowMediaPath` |
| `src/main/ipc.ts` | `handle('project:importPackage', …)` and `dialog:selectPackage` |
| `src/main/index.ts` | `requestSingleInstanceLock()`, parse `--import-package`, and handle `second-instance` to forward to the import, then tell the renderer to open the project |
| `src/preload/index.ts` + renderer `HomeScreen.tsx` | "Import Metachlorian package…" button. Show `project.handoff` rights banner in `EditorScreen.tsx` |
| `src/main/projects.ts` `loadProject` | Migration default: nothing needed (fields are optional) |

**Phase B: video B-roll inserts (I2)**

| File | Change |
|---|---|
| `src/shared/types.ts` | `BrollItem` adds `kind?: 'image' \| 'video'` (absent = image) and `mediaIn?: number` (seconds into the media file where the insert starts) |
| `src/main/pipeline/render.ts` (B-roll loop, ~L464–535) | For `kind==='video'`: input `-ss mediaIn -t (end-start) -i path` instead of `-loop 1 -t … -i`. Filter `setpts=PTS-STARTPTS+s/TB` before scale/crop/fades. Overlay `enable='between(t,s,e)'` unchanged. Insert audio is ignored (A-roll audio continues). The existing check that excludes fullscreen B-roll from crop `sendcmd` applies unchanged |
| `src/renderer/src/components/PreviewPlayer.tsx` `BrollOverlay` | Render `<video muted playsInline>` for video items and seek to `mediaIn + (time - start)` on each tick or play. `media://` already serves `projects/**` |
| `src/shared/tighten.ts` | When tighten removes time inside a video insert, either keep the insert continuous (preferred: protect insert ranges from pause removal, as `visualStory.protectedRanges` already does) or split it |
| `src/shared/editOps.ts` / `EditorScreen.tsx` | B-roll list shows a video thumbnail and duration. Existing enable/remove works unchanged |

**Phase C: Metachlorian as B-roll provider (I3)**

| File | Change |
|---|---|
| `src/main/settings.ts`, `SettingsModal.tsx` | `brollSource: 'web' \| 'metachlorian'`, `metachlorianUrl`, token stored encrypted like the API key, "Check connection" |
| `src/main/pipeline/brollProviders.ts` *(new)* | `metachlorian.search(query, trigger, ctx)`: `POST {url}/api/v1/search_shots` with `{query, filters:{shot_role:['b_roll'], quality_exclude:['major']}, rights:{usage:['marketing'], channels:['organic_social'], territories:[…], require:'allowed'}, limit:3}`, then `POST /api/v1/export_clip` (`preset: proxy_h264`, `crop:{aspect:'9:16', mode:'safe_crop'}`, `handles: 0`), then download to `projects/<id>/broll/`. Returns `{path, kind:'video', mediaIn:0, sourceUrl}`. The web provider wraps the existing `searchImage`/`downloadImage` |
| `src/main/pipeline/broll.ts` | `attachBroll` calls the selected provider. The LLM prompt asks for footage-style queries (e.g. "hands typing laptop close-up") when the provider is `metachlorian` |

The token needs scopes `library:read media:export`, as a service account or a
personal token. Rights filtering happens server-side.

## 6. Example manifest (validates against the schema)

```json
{
  "schema_version": "1.0.0",
  "kind": "metachlorian.package",
  "package_id": "01JA7Z3K8V5R2Q9W4M6T1X0B3C",
  "name": "Remote work explainer - rough cut",
  "created_at": "2026-10-04T10:15:00Z",
  "generator": { "name": "metachlorian", "version": "0.1.0", "instance": "https://media.example.org" },
  "brief": { "text": "30s vertical: founder soundbite about remote work, covered with calm B-roll of hands on keyboards. Organic social, GB.",
             "requested_by": { "type": "user", "id": "u_42" }, "agent": { "oauth_client_id": "claude-desktop" } },
  "target": { "consumer": "cutawan", "aspect": "9:16", "duration_sec": 30,
              "usage": ["marketing"], "channels": ["organic_social"], "territories": ["GB"] },
  "vocab_versions": { "shot_size": "1.0.0", "camera_movement": "1.0.0", "shot_role": "1.0.0", "mood": "1.0.0" },
  "media_policy": "stringout",
  "assets": [
    { "asset_id": "a_interview_01", "name": "Founder interview A-cam", "duration": 1834.2, "rate": "25/1",
      "width": 3840, "height": 2160, "start_timecode": "10:00:00:00", "reel": "A001", "has_audio": true,
      "language": "en-GB", "edit_type": "raw", "source_type": "own_production" },
    { "asset_id": "a_office_gv", "name": "Office GVs day 2", "duration": 412.0, "rate": "50/1",
      "width": 3840, "height": 2160, "has_audio": true, "edit_type": "raw", "source_type": "own_production" }
  ],
  "media": [
    { "file": "media/stringout_a_roll.mp4", "kind": "stringout", "duration": 24.0, "rate": "25/1",
      "width": 1920, "height": 1080, "video_codec": "h264", "audio_codec": "aac", "has_audio": true, "loudness_lufs": -14.0 },
    { "file": "media/it_02.mp4", "kind": "proxy", "asset_id": "a_office_gv", "asset_offset": 120.0, "duration": 6.0,
      "rate": "50/1", "width": 1920, "height": 1080, "video_codec": "h264", "audio_codec": "aac", "has_audio": true }
  ],
  "items": [
    { "item_id": "it_01", "shot_id": "s_8812", "asset_id": "a_interview_01", "role": "interview",
      "source_range": { "in": { "seconds": 612.4, "rate": "25/1", "frames": 15310, "timecode": "10:10:12:10" },
                        "out": { "seconds": 636.4, "rate": "25/1" } },
      "media": { "file": "media/stringout_a_roll.mp4", "in": 0.0, "out": 24.0 },
      "description": "Founder, MCU, says remote work is about trust not tools.",
      "tags": { "shot_size": ["medium_close_up"], "camera_movement": ["static"], "shot_role": ["interview"] },
      "transcript_excerpt": { "text": "Remote work was never about the tools. It's about trust.", "language": "en-GB" },
      "rights_ref": "r_own" },
    { "item_id": "it_02", "shot_id": "s_9001", "asset_id": "a_office_gv", "role": "b_roll",
      "source_range": { "in": { "seconds": 121.0 }, "out": { "seconds": 125.0 } }, "handles_sec": 1.0,
      "media": { "file": "media/it_02.mp4", "in": 1.0, "out": 5.0 },
      "description": "Close-up of hands typing on a laptop, slow push-in, soft window light.",
      "tags": { "shot_size": ["close_up"], "camera_movement": ["push_in"], "shot_role": ["insert", "b_roll"], "mood": ["calm"] },
      "safe_crops": { "9:16": { "rect": { "x": 0.34, "y": 0.0, "width": 0.316, "height": 1.0 } } },
      "rights_ref": "r_own" }
  ],
  "sequences": [
    { "sequence_id": "seq_main", "name": "Rough cut v1", "rate": "25/1", "width": 1920, "height": 1080, "duration": 24.0,
      "tracks": [
        { "name": "V1", "kind": "video", "role": "a_roll", "clips": [ { "item_id": "it_01", "record_in": 0.0, "duration": 24.0 } ] },
        { "name": "V2", "kind": "video", "role": "b_roll", "clips": [ { "item_id": "it_02", "record_in": 6.0, "duration": 4.0 } ] },
        { "name": "A1", "kind": "audio", "role": "a_roll", "clips": [ { "item_id": "it_01", "record_in": 0.0, "duration": 24.0 } ] } ] }
  ],
  "stringout": { "sequence_id": "seq_main", "file": "media/stringout_a_roll.mp4", "scope": "a_roll",
                 "transcript": "transcripts/stringout_a_roll.json", "map": [ { "item_id": "it_01", "in": 0.0, "out": 24.0 } ] },
  "transcripts": [ { "file": "transcripts/stringout_a_roll.json", "format": "cutawan.transcript/1",
                     "language": "en-GB", "time_base": "media", "media_file": "media/stringout_a_roll.mp4" } ],
  "timelines": [
    { "format": "otio", "version": "Timeline.1", "file": "timelines/seq_main.otio", "sequence_id": "seq_main", "media_paths": "relative" },
    { "format": "fcpxml", "version": "1.10", "file": "timelines/seq_main.fcpxml", "sequence_id": "seq_main", "media_paths": "relative" },
    { "format": "edl_cmx3600", "file": "timelines/seq_main.edl", "sequence_id": "seq_main", "media_paths": "missing" } ],
  "rights": {
    "verdict": "allowed",
    "intended": { "usage": ["marketing"], "channels": ["organic_social"], "territories": ["GB"], "start": "2026-10-04", "end": "2027-10-03" },
    "counts": { "allowed": 2, "restricted": 0, "blocked": 0, "unknown": 0 },
    "checked_at": "2026-10-04T10:14:58Z",
    "records": { "r_own": { "verdict": "allowed", "model_release": "unlimited", "property_release": "not_applicable",
                            "clearance_flags": [], "licence": { "name": "Own production" },
                            "permitted": { "usage": ["commercial", "editorial", "internal"], "channels": ["social", "web"], "territories": ["WORLD"] } } },
    "human_readable": "RIGHTS.md" },
  "cutawan": { "mode": "a_roll_with_inserts", "project_name": "Remote work explainer", "flow": "whole-video",
               "video_type": "talking-head", "aspect": "9:16", "captions": true, "auto_zoom": true,
               "inserts": [ { "item_id": "it_02", "start": 6.0, "end": 10.0, "mode": "fullscreen", "trigger": "tools" } ] }
}
```

## 7. Versioning and compatibility

* `schema_version` follows SemVer:
  * **minor**: new optional fields or enum values. Consumers ignore unknown
    enum values in non-critical fields such as `media.kind` and the
    `track.role` hint.
  * **major**: new required fields, or changed meanings.
* Metachlorian can write the previous major for 6 months after a major
  bump (`build_package(schema_major=1)`).
* `cutawan.mode` values unknown to an older Cutawan fall back to
  `stringout` when a stringout exists. Otherwise import fails with a clear
  message.
* Cutawan records `handoff.schemaVersion` in the project for later
  migrations.

## 8. Conformance tests (both repos)

* Metachlorian:
  * The golden manifests in `eval/fixtures/packages/` validate against the
    schema.
  * `.otio` round-trips through `otio.adapters.read_from_file`.
  * The FCPXML passes Apple DTD validation for 1.10.
  * The EDL re-reads with the CMX adapter to the same events.
  * Stringout duration equals the sum of map ranges ±1 frame.
  * Manual matrix per release: import into Resolve (latest), Premiere 26.x,
    FCP 12 and Avid MC 2026.x, and record results in `bench/interchange/`.
* Cutawan:
  * Unit tests for `importHandoffPackage`: valid, traversal, missing file,
    major 2, verdict blocked → warning.
  * Render test (offline, like `test-pipeline.ts`) with one video insert:
    the output has the insert frames between s and e and A-roll audio
    throughout.
  * A smoke test step that imports a fixture package under Xvfb.

## 9. Open questions

* Whether to burn the 9:16 safe crop into B-roll proxies (smaller, simpler
  for Cutawan) or ship 16:9 and let Cutawan crop. The proposal ships cropped
  proxies for `a_roll_with_inserts` and records the crop in
  `media[].crop`.
* Music beds: there is no Cutawan concept yet. Packages may include
  `audio` media and a `music` track. Cutawan ignores them until it has a
  music track.
* Headless export in Cutawan (`--export <project> --out <dir>`) would
  remove the final click. It is worth a separate Cutawan issue.
