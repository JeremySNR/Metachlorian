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

Core gaps found while building — all resolved in the core afterwards:
- Results carry identities as `identities`; `people` is the person count again.
- Responses give the person filter as `query.people: [{id, name}]`.
- A query made only of known names counts every match as strong.
- Names are unique: naming a second group with an existing name is refused with "merge them instead".
- Naming confirms faces as `named`; un-naming reverts exactly those (individual moves and merges stay).
- Face rows carry the file's `fps`.
- Merging a person into themselves returns 400 (ValueError handler), as it already did.
- Egress text says exactly what each model receives.
- Hosted providers ignore a leftover custom address, so it is no longer lost when switching back to Local.
- `/api/admin/providers` reports Codex installation, sign-in and today's budget even when Codex is not active.
