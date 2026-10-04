# M4 fresh review: Metachlorian web app

- Reviewer: independent design and UX review (a separate agent that did not read the app source).
- Date: 2026-10-04
- Inputs: `docs/design/system.md`, `docs/design/directions.md` (Edge Code), `README.md`, every journey in
  `review/m4/screens/` (desktop light and dark, laptop and tablet), and interactive checks with Playwright against the
  live instance at `127.0.0.1:8770`.
- Resolution of each finding: [fresh-review-fixes.md](fresh-review-fixes.md).

## Overall verdict

**The look and feel are on target, but the rights and privacy promises aren't safe yet.**

The visual language is a faithful Edge Code build: neutral surfaces in both themes with good light/dark parity; the mono
edge strip with dimmed leading timecode zeros; slate labels, hairlines and restrained density; solid 2 px focus rings
everywhere, a working skip link, landmarks and a usable keyboard path (`/` → `Ctrl+Enter` → arrows → `Enter`).

The problems are trust problems, and they sit on the product's two headline promises, "rights-aware" and "nothing leaves
this machine":

- **Blocked footage gets through three different ways.** The *Hide blocked* switch looks on but does nothing until you
  pick an intended use. Query-by-example reports cleared shots as *Rights unknown*. A *Blocked* shot exports as an MP4 in
  one click with no check.
- **Egress is mislabelled.** The model-adapter form labels `https://api.openai.com/v1` as **Local**.
- **AI output is presented more confidently than it should be.** Query chips look like hard filters but are only
  preferences. Card titles state low-confidence guesses as fact. A human correction doesn't reach the generated
  description.
- **Two WCAG AA failures block use outright**: at 320 CSS px the search field collapses to a sliver; in forced-colours
  mode, selected cards and the primary button's label disappear.

## Findings

| # | Sev | Surface | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| 1 | high | Search · filter rail · Rights | With intended use *Any use*, *Hide blocked* shows ON but is disabled, and blocked shots appear anyway. No disabled styling; *Verdict for this use* boxes checked-and-disabled. A blocked file is blocked for every use. | `02-inspector-why-it-matched--desktop-*`, `09-keyboard-grid-focus--desktop-light`. Live: `/search?q=close-up at night` → 7 of the first 18 cards *Blocked*. | Exclude blocked whatever the intended use; style inert controls as disabled and say why. |
| 2 | high | Search · query by example | Image-query results show every shot as *Rights unknown*, including cleared ones. | `02-query-by-example--desktop-dark`. | Run the same rights verdict, intended use and *Hide blocked* on `/api/similar`. |
| 3 | high | Shot detail · Export clip | A *Blocked* shot exports a proxy MP4 immediately; *Trimmed original* is offered too. Breaks §3.14 (export runs the rights check first). | Live: goldeneye shot 1590 → *Export clip → Proxy clip (MP4)* → download. | Route single-shot export through the rights check; disable media exports of blocked shots with the reason. |
| 4 | high | Settings → Model adapters | *Runs on this machine or our own network* defaults ON; typing `https://api.openai.com/v1` makes the badge read **Local**. Locality is self-declared. | Live (not saved). `08-model-adapters-egress--desktop-dark`. | Default off; classify the host (loopback, RFC 1918, `.local` = local; anything else remote); confirm before saving. |
| 5 | high | Search · parsed chips | Inferred preference chips look exactly like hard filter chips; "preferred" is only in the accessible name. The #1 result can miss three of five chips. | `01-search-results--desktop-*`. | Distinct visual state for preferences; "3 of 5 preferences matched" cue. |
| 6 | high | Global · reflow (WCAG 1.4.10) | At 320 CSS px the top bar doesn't reflow; the search field shrinks to ~14 px; every page scrolls horizontally. | Live at 320×640 on six routes. | Collapse nav into a menu below ~480 px; search on its own row. |
| 7 | high | Search grid · forced colours | Selection ring (box-shadow) vanishes; primary *Send to Cutawan* renders with no visible label. | Live, forced colours. | `outline: 2px solid Highlight` for selection; system colours for the primary button. |
| 8 | high | Inspector, Shot detail | Rights block and file name sit ~3,345 px down the inspector after ~40 signals; a blocked shot shows *Add to collection* and *Export* with no rights cue. | `05-search-blocked-visible--desktop-dark`. | Rights badge and file name in the inspector header; rights above signals; collapse quality metrics. |
| 9 | high | Processing status | During re-analysis all files show six ticked steps but "89% · Queued"; Library says "0 analysed · 63 in progress"; search shows "0 of 63 files analysed". | `08-ingest-processing--*`, `04-library-overview--*`, search banners. | Count searchable files as analysed; show re-analysis as its own state; banner only when files aren't searchable. |
| 10 | medium | Search · chip row | Chip row overflows with no scroll or fade; chips clipped or invisible while *Filters 5* claims five. | `01-search-results--desktop-*`, `03-technical-filters--*`. | Horizontal scroll with fade masks, or wrap; "+2" overflow chip. |
| 11 | medium | Search · strictness | The *Weaker matches below* divider is relative: a nonsense query shows ~24 "strong" results at *Strict*. Count never changes; not in the URL; *No shots match* never reached. | Live: "zzqxv underwater penguin ballet". | Absolute calibrated threshold; "No strong matches" state; strictness in URL and count. |
| 12 | medium | Card titles (AI honesty) | Titles concatenate model labels including low-band ones, stated as fact ("Extreme close-up… 2 people" from *41 low*). | `09-keyboard-shot-detail--desktop-dark`. | Leave out or mark low-band values; "suggested" cue. |
| 13 | medium | Corrections | A correction doesn't reach the generated description; text search can still match the old value. | `07-correction-*`. | Regenerate rule-based descriptions from effective values and re-index. |
| 14 | medium | Signals · multi-value rows | One meter at the maximum confidence for a multi-value row; the single ✗ removes only the last value. | Live aria on *Movement*. | Per-value confidence; remove × per value. |
| 15 | medium | Correction marker (a11y) | "Morning, Night" with Night struck through only visually; accessible name omits the model value. | `07-correction-human-marker--*`. | "Model said: Night (0.70)" on its own line, in the accessible name. |
| 16 | medium | Send to Cutawan | Intended use defaults to *Marketing · Organic social · GB* even when the search was *Any use*; cleared shots become restricted; "Send 0 shots". | `06-send-to-cutawan-dialog--*`. | Prefill from the search's intended use; say when a default is used. |
| 17 | medium | Send to Cutawan | Aspect defaults to 9:16 but shots with *No safe crop* get no warning. | Live. | Mark and summarise shots without a safe crop. |
| 18 | medium | Send to Cutawan (copy) | "Stringout" means two things; restricted prompt lacks a question mark and count. | `06-send-to-cutawan-dialog--*`. | Rename media option; "Include them?"; count on the primary. |
| 19 | medium | Asset header (rights) | Editorial-only, expiring file shows only "Expires 24 Oct". | `05-asset-expiring--*`. | Most restrictive fact first ("Editorial only · expires 24 Oct"). |
| 20 | medium | Selection (cards) | Only the focused card shows the checked box; others show a ring differing only by colour. | `06-selection-bar--*`. | Checked box visible on every selected card. |
| 21 | medium | Selection bar, pager | "Select all 120" next to "290 shots" selects the loaded page; pager reads "1 / 120" for 292 results. | `06-selection-bar--*`, `02-shot-detail--*`. | Select all by query; pager on the total. |
| 22 | medium | Coverage matrix (light) | `#f4f4f4` on `--viz-3` (`#737373`) = 4.31:1, fails 1.4.3. | Live computed colours. | Dark text on `--viz-3` or darken it. |
| 23 | medium | Tablet · coarse pointer | 81 targets under 44 px (chip actions 24×22, card actions 24×24); overlay actions always cover footage. | Live 768×1024 touch. | `--target-coarse` 44 px; overlay actions only on the focused card. |
| 24 | medium | Tablet · filter drawer | No title, no close button; overlays the top bar. | `03-filter-drawer--tablet-dark`. | Sticky header "Filters · 5" with a close button. |
| 25 | medium | Tablet · rights feedback | "87 shots hidden by rights for this use" only inside the drawer. | `05-search-intended-use-marketing--tablet-dark`. | Show it in the results status line at every breakpoint. |
| 26 | medium | Shot detail · Similar shots | No rights glyph on similar-shot cards. | `02-shot-detail--tablet-dark`. | Standard edge strip with the rights glyph. |
| 27 | medium | Why it matched (filters) | Raw strings: "filter: log: False", "filter: min height: 1080". | `03-technical-filters--desktop-*`. | Human copy, grouped under "Matches your filters". |
| 28 | medium | Frame rates | Measured averages shown (59.98p, 30.01p, 24.03p). | `01-search-results--*`. | Snap to standard rates within ±0.1%; exact value in a tooltip. |
| 29 | medium | Corrections log | No shot number, timecode or previous value. | `07-corrections-log--*`. | "file › Shot 3 · 00:00:08:21" and "Night → Morning". |
| 30 | medium | Page titles and headings | `document.title` is "Metachlorian" everywhere; Search and Collections have no `h1`; unknown routes render *Appearance*. | Live, 8 routes. | Per-route titles; hidden `h1`s; not-found page. |
| 31 | low | Results grid (screen readers) | Row labels concatenate three cards; card names don't say which number is the timecode. | Live aria. | "Row 2 of 30"; "Starts 1 min 6 s 5 fr, 4 seconds long. Restricted: credit required." |
| 32 | low | Shortcut sheet | Keys run together ("CtrlK"); Mac glyphs mixed with PC words on Linux. | `09-shortcuts--desktop-dark`. | One `kbd` per key, platform-specific. |
| 33 | low | Ingest · accent | All 63 progress bars are magenta; §0 reserves it for the current item. | `08-ingest-processing--*`. | `--fg-2` fills; magenta only for the active row. |
| 34 | low | Asset view | Raw edit-stage scores; "1 steps left"; mixed date formats; "12.49" vs "12.5"; empty MATCHES lane unexplained. | `04-asset-view-edit-stage--*`. | Normalise, pluralise, one date format, empty-lane message. |
| 35 | low | Search error state | HTTP 500 shows "0 shots" and "didn't respond". | Live, routed 500. | Hide the count; wording that fits the failure. |

Not re-raised (already in `findings.md`): H.264 in Playwright, grid scroll performance, the hand-rolled grid, Electron
drag-out, no sort control, no per-verdict rail counts, no captions track, coverage-matrix shape.

Side effects of the review: one proxy-clip export written (finding 3); one time-of-day correction made and reverted; the
model-adapter form was typed into but not saved.
