# M4 review artefacts: the Metachlorian web app

- Date: 2026-10-04
- Build: `app/` (React 19.3, TypeScript 6.0, Vite 8, React Aria Components 1.21, TanStack Query/Router/Virtual, Zustand, Lucide)
- Served by: the demo core on `http://127.0.0.1:8770` (63 files, ~293 shots), reading `app/dist`
- Regenerate: `cd app && npm run build && npm run review:capture` (Playwright 1.56.1 with `/opt/pw-browsers`, under `xvfb-run`)
- Results: `e2e-results.json` (11/11 passed), `capture.log`, `perf-web.json`, `perf-electron.json`
- Findings and known gaps: [`findings.md`](findings.md)

Screenshot names are `<journey>-<view>--<viewport>-<theme>.jpg`. Viewports: **desktop** 1440×900, **laptop**
1024×768 (overlay inspector), **tablet** 768×1024 (filter drawer, sheet inspector). Most views exist in all six
combinations; dialogs and transient states are captured at desktop only. Every screenshot is taken with
reduced motion, so no transition is mid-flight.

## Videos (`video/`, WebM, 1440×900)

| File | Journey |
|---|---|
| `01-search-natural-language-to-shot-results-with-previews.webm` | `/` focuses search, type "handheld street food close-ups, busy, night", chips appear, hover scrub, dwell preview |
| `02-select-a-shot-and-find-similar.webm` | Click a card → inspector with *Why it matched* → Find similar → query by example (image picked on the search bar) → laptop overlay sheet → Shot detail with similar shots |
| `03-filter-by-resolution-fps-orientation-log-and-duration.webm` | Technical filters in the rail (1080p+, ≥ 25 fps, horizontal, not log, 2–10 s), chips mirror them, tablet filter drawer with *Show N shots* |
| `04-see-whether-a-file-is-raw-selects-or-finished.webm` | Library overview (edit-stage distribution, rights, coverage matrix and gaps) → Asset view with raw/selects/finished evidence scores and filmstrip |
| `05-rights-releases-and-expiry-respected-by-intended-use-search.webm` | Rights editor (cleared, editorial only, expiry in 20 days, model release) → file shows *Expires* → search with intended use Marketing · GB hides that file and reports "N shots hidden by rights" → *Rights and governance* expiring tab. Original rights restored afterwards. |
| `06-build-a-cutawan-package-from-a-collection.webm` | Create a collection, select three shots with `X`, add with `B`, keyboard reorder (`Alt+↓`), Send to Cutawan dialog with live rights check and the explicit restricted choice, package built, folder path and download shown. Collection deleted afterwards. |
| `07-correct-a-wrong-tag-it-is-marked-human-and-survives-reload.webm` | Shot detail → edit *Time of day* → toast "This tag will stay as you set it…" → human marker chip with the model's value struck through → reload: still human → Corrections log. Correction reverted afterwards. |
| `08-processing-status-is-visible.webm` | Re-analysis queued for the shortest file → Ingest (summary, sources, drop zone, queue steps, analysers incl. "no vision-language model configured, CPU tier") → Model adapters egress → API tokens |
| `09-keyboard-only-search-to-inspector-to-shot-detail.webm` | `/`, type, `Ctrl+Enter` focuses the first result, arrows, `Space` preview, `X` select, `Esc`, `Ctrl+K` command menu, `?` shortcuts, `Enter` → Shot detail with the player focused, `L`/`K`, `I`, frame steps, `O` |
| `10-grid-scroll-smoothness.webm` | Browse all shots at size S and scroll the virtualised grid end to end twice (frame timings in `perf-web.json`) |
| `11-electron-preview-latency.webm` | The same web UI inside Electron 39 (H.264 decode): `Space` previews on eight cards and dwell previews on three; start times in `perf-electron.json` |

## Screenshots (`screens/`)

### 01 Search
- `01-search-results--{desktop,laptop,tablet}-{dark,light}.jpg`: three-pane search; parsed chips (*SHOT SIZE Close-up*, *MOVEMENT Handheld*, …) with dotted underline for inferred values and a pin to require them; filter rail with live facet counts; edge-strip cards (timecode with dimmed leading zeros, duration, fps, rights glyph); inspector following focus. Laptop collapses the inspector to an overlay sheet; tablet turns the rail into a drawer.
- `01-search-hover-scrub--desktop-dark.jpg`: sprite-sheet scrub with the 2 px scrub bar.
- `01-search-hover-preview--desktop-dark.jpg`: dwell preview from the pooled `<video>` (Playwright's Chromium cannot decode H.264, so the frame is the sprite; see 11 for real playback).

### 02 Similar and shot detail
- `02-inspector-why-it-matched--desktop-{dark,light}.jpg`: inspector with player, description, in/out, technical line and *Why it matched* mapping the person's words to signals (“close-ups” → shot size: Close-up, confidence meter).
- `02-similar-results--*.jpg`: *SIMILAR TO* chip and similar shots.
- `02-query-by-example--desktop-dark.jpg`: results for an image chosen on the search bar (`POST /api/similar`).
- `02-inspector-sheet--laptop-dark.jpg`: laptop overlay sheet.
- `02-shot-detail--*.jpg`: Shot detail (player + transport, *Why it matched*, transcript, moments, similar shots; signals grouped with source and confidence; rights; collections; file).

### 03 Technical filters
- `03-technical-filters--*.jpg`: resolution, fps, orientation, log and duration applied; chips mirror the rail; result count updates.
- `03-filter-drawer--tablet-dark.jpg`: tablet drawer with the sticky *Show 64 shots* / *Reset* footer (staged, batch-applied).

### 04 Raw / selects / finished
- `04-library-overview--*.jpg`: plain figures (files, shots, hours, throughput), edit-stage bars, rights distribution with icon + word + count, coverage matrix on the neutral ramp with hatched *gap* cells (each cell runs that search), biggest gaps.
- `04-asset-view-edit-stage--*.jpg`: Asset view header (editable edit stage menu, shot count, length, rights), player, edit-stage classification with evidence scores, summary, technical metadata, filmstrip (matches / shots / rights / ruler), structure stats, shot table.

### 05 Rights
- `05-rights-editor--desktop-{dark,light}.jpg`: per-file rights editor (status, vocab-backed uses and channels, territories, start/expiry, releases, brand safety, licence, credit).
- `05-asset-expiring--*.jpg`: the file now shows *Expires 24 Oct*.
- `05-search-intended-use-marketing--*.jpg`: intended use Marketing · GB; verdict filters; "N shots hidden by rights for this use"; *RIGHTS* chip.
- `05-search-blocked-visible--desktop-dark.jpg`: with blocked shots shown: hatched frames and *Blocked* chips.
- `05-rights-governance--*.jpg`: *Rights and governance*, *Expiring soon* tab with bulk actions.

### 06 Collections and Cutawan handoff
- `06-collection-empty--desktop-*.jpg`: new collection, empty state.
- `06-selection-bar--*.jpg`: three selected (Key ring, checked box), selection bar with *Add to <collection>*, *Find similar*, *Export*, primary *Send to Cutawan*.
- `06-collection--*.jpg`: ordered shots with trim, note, rights badges and drag handles; rights summary in the header.
- `06-send-to-cutawan-dialog--desktop-*.jpg`: package name, aspect, brief, mode, media, intended use, live rights summary with credits, the restricted decision, shot list showing what is left out.
- `06-package-ready--desktop-*.jpg`: package folder path and *Download package (.zip)*.

### 07 Corrections
- `07-correction-human-marker--desktop-*.jpg`: corrected value with the inverse human chip and the model's value struck through, plus the "it sticks" toast with *Undo*.
- `07-correction-after-reload--*.jpg`: still marked human after reload.
- `07-corrections-log--*.jpg`: corrections log with *Revert*.

### 08 Processing and admin
- `08-ingest-processing--*.jpg`: ingest summary, watched folders, add folder / S3, drop zone, queue with step glyphs (Probe · Proxies · Shots · Vision · Audio · Index) and progress, analyser availability.
- `08-model-adapters-egress--desktop-*.jpg`: *Local* / *Leaves this machine* status, CPU-tier explanation, VLM and LLM endpoint forms, bundled models.
- `08-api-tokens--desktop-*.jpg`: tokens table and copy-paste MCP config (stdio `metachlorian --data … mcp` and HTTP `/mcp` with a bearer).

### 09 Keyboard
- `09-keyboard-grid-focus--desktop-*.jpg`: focus ring outside the Key selection ring on a focused, selected card.
- `09-command-menu--desktop-dark.jpg`, `09-shortcuts--desktop-dark.jpg`: ⌘K command menu and the `?` shortcut sheet.
- `09-keyboard-shot-detail--desktop-*.jpg`: player focused, in/out marked from the keyboard (IN/OUT/DUR readout and range tint).

### 11 Electron
- `11-electron-space-preview--desktop-dark.jpg`, `11-electron-dwell-preview--desktop-dark.jpg`: real in-card H.264 preview playback in Electron.
