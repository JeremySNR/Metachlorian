# M4 findings

Two passes: the builder's own review while capturing (this section), then an independent review by a fresh reviewer that
had not seen the code (`review/m4/fresh-review.md`).

Severity: high = broken or misleading, medium = noticeably wrong or missing from the brief, low = polish or a documented gap.

## Builder pass — fixed during review

| Sev | Finding | Fix |
|---|---|---|
| high | Inspector player collapsed to zero height in its column | Columns no longer let the player shrink (`flex: none`) |
| high | Query chips crashed the page: a React Aria button inside a tag needs a slot | The pin control is a plain button; Enter on the chip does the same |
| high | Send to Cutawan with "A-roll with inserts" and no A-roll shot returned HTTP 500 (core bug) | Dialog defaults to Stringout and explains why; the core now returns a 400 with a clear message (regression test) |
| high | Player focus ring invisible in the light theme (the player root forced the dark scheme) | Dark scheme scoped to the player's children |
| medium | Edit stage facet listed every term at 0 | Only terms with shots, or selected, plus "Show all 12" |
| medium | Cards re-rendered on every scroll frame (React Compiler skips the grid) | Cards memoised, callbacks stable |
| medium | ⌘Enter focused a card from the stale results, then lost focus | Focus waits for the new results |
| medium | Meaningless confidence meter on raw cosine similarity in "Why it matched" | Rank and source shown instead; vocabulary rows show "words" → field: value and confidence |
| medium | Spinner stuck when the proxy can't be decoded | Video errors clear the loading state |
| medium | `composes` in descendant selectors broke the Lightning CSS build | Declarations expanded |
| low | Meter shown on empty signal values; comma spacing in multi-term values; asset title truncated at 768 px; ingest step labels overflowed on tablet; underlined coverage cells; duplicated rights summary in the dialog footer | All fixed |

## Builder pass — open

| Sev | Finding |
|---|---|
| medium | Playwright's Chromium has no H.264, so preview latency is measured in Electron 39 instead: median 93 ms idle, 179 ms with the core's workers busy; p90 > 300 ms under that load |
| medium | Grid scroll in headless software rendering: p95 29–45 ms per frame without recording, 79 ms with recording. Needs the ADR 013 bench on real hardware with 10,000+ results |
| medium | Results grid is a hand-rolled ARIA grid over TanStack Virtual instead of React Aria GridList (ADR 013's documented fallback, deliberate: Space previews rather than selects, placeholders, per-frame scrubbing) |
| medium | In Electron, native drag-out bypasses in-app drop targets (keyboard and buttons still work) |
| low | No sort control (API has none); suggestions cover tags and recent searches only; no shortcut remapping; no captions track; no hover-preview popover; no filmstrip drag-trim (I/O keys and the trim dialog cover it); ingest step glyphs approximate between polls; coverage matrix is facet × value, not place × topic; no per-verdict counts in the rights rail; no Stylelint rule or contrast script; TypeScript 6 (typescript-eslint supports < 6.1); journey 08 queues a rollup re-analysis of the shortest demo file |

Captures: `screens/` (desktop 1440×900, laptop 1024×768, tablet 768×1024, light and dark), `index.md`, `perf-web.json`,
`perf-electron.json`, `e2e-results.json`. Journey videos are written to `video/` by `npm run review:capture` and are not
committed (27 MB).

## Model providers and People (builder pass)

| Sev | Finding | State |
|---|---|---|
| medium | A name-only search ("Jonah Fielding") came back as *No strong matches*: the core's match strength ignores the person filter | Worked around in the app (a query that is only known names is a filter, no strong/weak split); core gap below |
| medium | Journey 08's adapter form moved under the *Local* provider; saving now needs a model as well as an endpoint before anything can leave | Journey updated |
| low | Dialog captures were taken mid-fade | Captures wait for the dialog to settle |

Core gaps found while building (not fixed here; `core/` is out of scope):
- Search results' `people` (identities) overwrites the summary's `people` count, so results no longer carry the person count (the app's types omit it).
- The person filter is only reported as a sentence in `notes`; the app reads `query.require.person` instead. A structured `query.people: [{id, name}]` would be sturdier.
- Match strength does not count a person filter as evidence (name-only queries score as weak).
- Names are not unique: two identities may share a name and `/api/search` then filters by only one of them. The app offers *Merge into …* when a typed name already exists.
- Naming (`PATCH /api/people/{id}`) marks every face of the cluster as confirmed (`assigned_by='human'`); unnaming doesn't undo that, so a journey's "restore" leaves the faces confirmed.
- Face rows (`/api/people/{id}`) carry no frame rate or timecode; the app looks the fps up from `/api/assets`.
- `POST /api/people/{id}/merge` with `into` equal to the id raises a `ValueError` (likely a 500, not a 400).
- `egress.adapters[].sends` says the language model sends "queries", but search never calls the language model (only fusion and rollup do).
- Switching an endpoint to a hosted provider clears its custom `base_url`; there is no per-provider memory, so the custom address must be retyped after a round trip (the app remembers it until the form is saved).
- `/api/admin/providers` reports Codex status and remaining requests only for the active endpoint; a quick "is Codex set up" for an inactive provider needs `POST /api/admin/providers/test`.
