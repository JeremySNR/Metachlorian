# M4 review artefacts: the Metachlorian web app

- Date: 2026-10-04
- Build: `app/` (React 19.3, TypeScript 6.0, Vite 8, React Aria Components 1.21, TanStack Query/Router/Virtual, Zustand, Lucide)
- Served by: the demo core on `http://127.0.0.1:8770` (63 files, ~293 shots), reading `app/dist`
- Regenerate: `cd app && npm run build && npm run review:capture` (Playwright 1.56.1 with `/opt/pw-browsers`, under `xvfb-run`)
- Results: `e2e-results.json` (15/15 passed), `capture.log`, `perf-web.json`, `perf-electron.json`
- Findings and known gaps: [`findings.md`](findings.md); the independent review is [`fresh-review.md`](fresh-review.md) and its resolutions [`fresh-review-fixes.md`](fresh-review-fixes.md). Captures were re-taken after those fixes.

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
| `05-rights-releases-and-expiry-respected-by-intended-use-search.webm` | Rights editor (cleared, editorial only, expiry in 20 days, model release) → file shows *Editorial only · expires …* → search with intended use Marketing · GB hides that file and reports "N shots hidden by rights" in the status line → with Any use no blocked card shows (*Hide blocked* on by default) → *Hide blocked* switched off shows the file's shots hatched (`blocked=show`) → *Rights and governance* expiring tab. Original rights restored afterwards. |
| `06-build-a-cutawan-package-from-a-collection.webm` | A blocked shot's *Export clip* menu with media exports disabled and the reason (the core answers 403 too), then: create a collection, select three shots with `X`, add with `B`, keyboard reorder (`Alt+↓`), Send to Cutawan dialog with live rights check and the explicit restricted choice, package built, folder path and download shown. Collection deleted afterwards. |
| `07-correct-a-wrong-tag-it-is-marked-human-and-survives-reload.webm` | Shot detail → edit *Time of day* → toast "This tag will stay as you set it…" → human marker chip with the model's value struck through → reload: still human → Corrections log. Correction reverted afterwards. |
| `08-processing-status-is-visible.webm` | Re-analysis queued (rollup on the shortest file, the embedder on six short files) → Ingest: those files stay *Searchable* and read *Updating: embed* (summary, sources, drop zone, queue steps, analysers incl. "no vision-language model configured, CPU tier") → Model adapters: a public endpoint typed, classified by the core as remote, save asks first (cancelled, then a loopback endpoint reads *Local*; nothing saved) → API tokens |
| `09-keyboard-only-search-to-inspector-to-shot-detail.webm` | `/`, type, `Ctrl+Enter` focuses the first result, arrows, `Space` preview, `X` select, `Esc`, `Ctrl+K` command menu, `?` shortcuts, `Enter` → Shot detail with the player focused, `L`/`K`, `I`, frame steps, `O` |
| `10-grid-scroll-smoothness.webm` | Browse all shots at size S and scroll the virtualised grid end to end twice (frame timings in `perf-web.json`) |
| `13-hosted-model-providers-what-each-unlocks-and-costs-what-leaves-write-only-keys.webm` | Settings → Model adapters: status (captions, summaries, queue), provider chooser (Local / OpenAI / OpenRouter / ChatGPT via Codex) with what each unlocks, speed and cost; OpenAI shows *Leaves this machine* with what is sent and never sent; a fake key saved (password field, shown only as `sk-te…abcd` · stored in this library, never echoed by the page or the API); *Save model settings* asks first (§3.20), **cancelled**, nothing hosted saved and the top bar still reads *Local*; *Remove key*; OpenRouter (catalogue offline here → free-text model fallback); Codex setup (not installed, the two commands, daily cap); different provider for summaries; discarded; 320 px |
| `14-people-name-someone-search-by-name-merge-not-this-person-restore.webm` | People: unnamed person named inline (“Jonah Fielding”) → appears under Named → search for the name: `PERSON` chip, the core's hard filter, the inspector's People row → Shot detail People row (unnamed people offer *Name…*) → person page → renamed back to unnamed. Drag one tile onto another (opens merge, cancelled), then select two clusters of the same man in `head-pose-face-detection-female-and-male.mp4` and *Merge 2 people* (larger kept) → on the merged person, *Not this person* on the merged face moves it out again to a new person → *Forget this person* dialog (cancelled; nobody forgotten) → Privacy and analysis settings → 320 px |
| `15-search-inside-a-folder-or-a-collection.webm` | Library → *Folders* (files, shots, length, shoot dates, edit stages per folder) → *Show files* on `sample` (from `/api/assets?folder=`) → *Search this folder*: every result's `folder` is inside `sample`, the `In sample` scope chip leads the chip row, the count reads "27 shots in sample · …", the search box has focus, the inspector shows the folder breadcrumb → *Find similar* and query by example (an image) stay inside `sample` (`filters.folder`; `POST /api/similar?folder=…`) → the rail's *Scope* control (Everything / a folder / a collection, searchable tree) → tablet drawer with the same control → typing `folder:"extra" night`: the core strips the words and echoes `query.filters.folder`, a scope chip *from your words*, results only from `extra`; removing the chip edits the words → `?folder=samples`: *No folder called “samples”* with *Search in sample* (one click) and *Search every folder* → `Disney 2025` (no close match) → ⌘K *Search in folder…* → `extra` → Ingest sources with *Search this folder* / *Show files* → a temporary collection with two shots → *Search in this collection*: exactly those two shots, *In collection:* chip, focus in the search box. Collection deleted afterwards. 320 px reflow checked on Folders and scoped search. |
| `12-narrow-screens-forced-colours-and-match-strength.webm` | 320×640: no sideways scroll on ten routes (now including People, a person, Model adapters and Privacy), search on its own row, sections menu; forced colours with two selected cards; a nonsense query at *Strict* shows *No strong matches*; strictness in the URL |
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
- `05-asset-expiring--*.jpg`: the file now leads with the most restrictive fact: *Editorial only · expires 24 Oct*.
- `05-search-intended-use-marketing--*.jpg`: intended use Marketing · GB; verdict filters; "N shots hidden by rights" in the results status line at every breakpoint (and in the rail); *RIGHTS* chip.
- `05-search-blocked-visible--desktop-dark.jpg`: *Hide blocked* switched off (`blocked=show` in the URL): hatched frames and *Blocked* chips. With *Hide blocked* on (the default), blocked footage is hidden whatever the intended use.
- `05-rights-governance--*.jpg`: *Rights and governance*, *Expiring soon* tab with bulk actions.

### 06 Collections and Cutawan handoff
- `06-export-blocked-shot--desktop-dark.jpg`: Shot detail of a blocked shot: the rights cue by the actions, and *Export clip* with the media items disabled and the reason up front (the core also answers 403).
- `06-collection-empty--desktop-*.jpg`: new collection, empty state.
- `06-selection-bar--*.jpg`: three selected (Key ring and a checked box on every selected card), selection bar with *Select all N* (every result of the query), *Add to <collection>*, *Find similar*, *Export*, primary *Send to Cutawan*.
- `06-collection--*.jpg`: ordered shots with trim, note, rights badges and drag handles; rights summary in the header.
- `06-send-to-cutawan-dialog--desktop-*.jpg`: package name, aspect, brief, mode, media (renamed: *One rendered video*, *Proxy clips*, …), intended use prefilled from the search and saying where it came from, live rights summary with credits and *no safe 9:16 crop* warnings, the restricted question ("Include them?"), shot list showing what is left out.
- `06-package-ready--desktop-*.jpg`: package folder path and *Download package (.zip)*.

### 07 Corrections
- `07-correction-human-marker--desktop-*.jpg`: corrected value with the inverse human chip, the model's value struck through and *Model said: Night (0.70)* on its own line (also in the row's accessible name); multi-value rows show a confidence and a remove button per value; the "it sticks" toast with *Undo*.
- `07-correction-after-reload--*.jpg`: still marked human after reload.
- `07-corrections-log--*.jpg`: corrections log with file › shot number · timecode, *Night (0.70) → Morning*, and *Revert*.

### 08 Processing and admin
- `08-ingest-processing--*.jpg`: ingest summary (searchable / not yet searchable), watched folders, add folder / S3, drop zone, queue with step glyphs (Probe · Proxies · Shots · Vision · Audio · Index) and progress in `--fg-2` (Key only for the current row), the re-analysed file shown as *Searchable · Updating: …* instead of a percentage, analyser availability.
- `08-ingest-updating--desktop-dark.jpg`: a re-analysed file mid-refresh: *Searchable · 1 step left*, *Updating: visual tags*, only the refreshing step spinning.
- `08-model-adapters-egress--desktop-*.jpg`: *Local* with your own server: `https://api.openai.com/v1` typed (not saved); the badge is the core's classification of the host (*Leaves this machine*), even with the self-declared switch on.
- `08-model-adapters-confirm--desktop-dark.jpg`: saving a remote endpoint asks first (§3.20), naming the host. Cancelled.
- `08-api-tokens--desktop-*.jpg`: tokens table and copy-paste MCP config (stdio `metachlorian --data … mcp` and HTTP `/mcp` with a bearer).

### 13 Model providers (Settings → Model adapters)
- `13-model-providers--{desktop,laptop,tablet}-{dark,light}.jpg`: *Status* (captions and summaries: provider · model · health; files waiting for captions from `/api/processing` `pending`; the caption analyser's reason when it is unavailable; *Local* / *Leaves this machine*), the provider chooser for captions with what each costs and the *Local* / *Leaves this machine* chip on every option, *Unlocks / Speed / Cost* for the selected one, the custom endpoint form, summaries following the captions provider, bundled models.
- `13-provider-openai-key--desktop-{dark,light}.jpg`: OpenAI selected: key saved and shown only as `sk-te…abcd · stored in this library`, password field empty, *Remove key*, *Test*; *Sent* / *Never sent* lists.
- `13-provider-confirm--desktop-dark.jpg`: the §3.20 confirmation: “Frames and text from your footage will be sent to OpenAI (api.openai.com)”, per role what is sent, never sent, *Turn on and send frames* (cancelled).
- `13-provider-openrouter--desktop-dark.jpg`: OpenRouter with the catalogue unreachable (core 502): free-text model with the suggested default. With a connection the picker lists models with a *Reads images* filter, $/M input and output, context and JSON support.
- `13-provider-codex--desktop-{dark,light}.jpg`: ChatGPT via Codex: setup state (CLI not found here), `npm i -g @openai/codex`, `codex login`, “never reads your login tokens”, CLI path, requests-per-day cap and the plan cost line.
- `13-provider-separate-summaries--desktop-dark.jpg`: *Use a different provider for summaries* with its own chooser.
- `13-model-providers--320-dark.jpg`: 320 px, chooser stacked.

### 14 People (face identity)
- `14-people--{desktop,laptop,tablet}-{dark,light}.jpg`: privacy line (matched here, never sent, can be forgotten, link to settings), *Named*, *Unnamed: help name them* (largest first) with face crops, counts and *Name this person*.
- `14-people-naming--desktop-dark.jpg`, `14-people-named--desktop-dark.jpg`: inline naming; the person moves to *Named*.
- `14-search-person--desktop-{dark,light}.jpg`: a search for the name: `PERSON · Jonah Fielding` chip (Enter opens the person), a name-only query treated as a filter (no strong/weak split), the inspector's *People* row.
- `14-shot-people--*.jpg`: Shot detail *People* row: face chips linking to each person; unnamed ones offer *Name…*.
- `14-person-named--desktop-dark.jpg`, `14-person--*.jpg`: a person: actions (*Find shots with this person*, *Name/Rename*, *Merge into…*, *Forget this person*), faces grouped by file with shot number and timecode, *Confirmed* marks, *Not this person*.
- `14-people-selection--desktop-{dark,light}.jpg`, `14-merge-dialog--desktop-dark.jpg`: two selected (Key ring and check), selection bar, merge dialog choosing who to keep.
- `14-not-this-person--desktop-dark.jpg`: the face moved to a new person, toast with *Undo*.
- `14-forget-confirm--desktop-dark.jpg`: forget confirmation naming what is deleted (cancelled).
- `14-privacy-settings--desktop-{dark,light}.jpg`: Settings → Privacy and analysis: face recognition switch and the facts about face data; where analysis runs.
- `14-people--320-dark.jpg`: 320 px.

### 15 Search scope: folders and collections
- `15-library-folders--{desktop,laptop,tablet,320}-{dark,light}.jpg`: Library → *Folders*: each folder that holds footage, nested under its watched folder, with files, shots, length, shoot-date range ("20 Oct 2013 – 4 Oct 2026") and the edit stages of its files; *Search this folder* and *Show files* per row. At 320 px the facts and actions stack under the name.
- `15-folder-files--desktop-{dark,light}.jpg`: *Show files* on `sample`: file, shoot date, length, edit stage and rights (subfolder shown under the name when the file is deeper).
- `15-search-in-folder--{desktop,laptop,tablet,320}-{dark,light}.jpg`: search scoped to `sample`: the *SCOPE* control at the top of the rail (*In sample*, with a clear button), the filled, folder-iconed *In sample* chip first in the chip row (distinct from filter chips), the count "27 shots in sample · 6 files · 24 shots hidden by rights", facet counts for the folder only, and the folder breadcrumb under the file name in the inspector (each part scopes search to that folder).
- `15-scope-picker--desktop-{dark,light}.jpg`: the Scope popover: *Everything / A folder / A collection*, *Find a folder*, folder tree with files, shoot dates and length, the current folder checked.
- `15-scope-drawer--tablet-{dark,light}.jpg`: the same control at the top of the tablet filter drawer (staged, applied with *Show 27 shots*).
- `15-typed-folder--desktop-{dark,light}.jpg`: `folder:"extra" night`: the chip comes from the core's `query.filters` (dotted underline: from your words), the rail says "From your words: In extra", the time-of-day preference chip beside it, "242 shots in extra".
- `15-folder-not-found--desktop-{dark,light}.jpg`: `?folder=samples`: the core's note as the empty state, *No folder called “samples”*, "The closest folder is **sample**", *Search in sample* (one click) and *Search every folder*.
- `15-command-search-in-folder--desktop-dark.jpg`: ⌘K → *Search in folder…* opens the same chooser in a dialog (also *Search in collection…*).
- `15-ingest-sources--desktop-{dark,light}.jpg`: Ingest → watched folders: *Search this folder* and *Show files* (opens Library → Folders with the files listed).
- `15-collection-search-action--desktop-{dark,light}.jpg`: a collection's header with *Search in this collection*.
- `15-search-in-collection--desktop-{dark,light}.jpg`: the result: exactly the collection's two shots, *In collection: …* chip, "2 shots in collection … · 2 files", focus in the search box (its recent-search list open, as on any focus).

### 09 Keyboard
- `09-keyboard-grid-focus--desktop-*.jpg`: focus ring outside the Key selection ring on a focused, selected card.
- `09-command-menu--desktop-dark.jpg`, `09-shortcuts--desktop-dark.jpg`: ⌘K command menu and the `?` shortcut sheet.
- `09-keyboard-shot-detail--desktop-*.jpg`: player focused, in/out marked from the keyboard (IN/OUT/DUR readout and range tint).

### 12 Reflow, forced colours, match strength
- `12-reflow-search--320-{dark,light}.jpg`: search at 320×640: sections in a menu, search field on its own row at full width, chips wrap, header controls wrap, one column of cards.
- `12-reflow-sections-menu--320-dark.jpg`: the sections menu.
- `12-forced-colours-selection--desktop.jpg`: forced colours (Playwright `forcedColors: 'active'`): selected cards keep a Highlight outline and checked box; the primary *Send to Cutawan* keeps its label.
- `12-no-strong-matches--desktop-dark.jpg`: "zzqxv underwater penguin ballet" at *Strict*: *No strong matches* with suggestions, the weaker matches listed below, "0 strong (strict)" in the count.

### 11 Electron
- `11-electron-space-preview--desktop-dark.jpg`, `11-electron-dwell-preview--desktop-dark.jpg`: real in-card H.264 preview playback in Electron.
