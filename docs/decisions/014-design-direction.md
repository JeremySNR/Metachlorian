# 014. Design direction: Edge Code

- Status: accepted
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context

The UI is Metachlorian's primary differentiator. It must not look like a generic admin dashboard or a
templated component library. It must:

- serve editors, content/marketing leads, admins and AI agents (through the same data the UI shows);
- be desktop first (Electron), also served on the web, and responsive to tablet;
- have light and dark themes and meet WCAG 2.2 AA with full keyboard operation;
- stay smooth across thousands of thumbnails, with instant scrub and < 300 ms preview start;
- feel like a sibling of Cutawan (near-monochrome dark, one accent, Lucide) without cloning it.

Research (`docs/design/research.md`) found twelve patterns. The most constraining are:

- the shot is the unit of search;
- hover-scrub must be instant and intentional;
- governance belongs on the card;
- calm comes from restraint;
- **surfaces around footage must be colour-neutral** (grading-suite practice);
- fixed, familiar panel geometry beats novel chrome.

Three directions were developed and scored (`docs/design/directions.md`).

## Options considered

The template's columns are adapted to design directions: *Quality* is fit to the user stories, *Licence* is
font licensing, *Hardware* is rendering cost, *Speed* is perceived speed, *Maturity* is how proven the idiom
is, and *Maintenance* is the cost to keep it consistent.

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **A. Edge Code**: neutral suite-grey surfaces, magenta *Key* accent, Instrument Sans + JetBrains Mono, edge-strip metadata, squarer forms | Highest on search, rights, corrections and technical filters (weighted score 162/170) | OFL (both fonts) | Cheapest: solid surfaces, no blur | Fast, mechanical motion (80–180 ms) | NLE idiom (Resolve, FCP, Avid) refined | Low: one neutral ramp generates both themes |
| B. Light Table: warm paper, chinagraph red, Newsreader + Hanken Grotesk + IBM Plex Mono, contact-sheet strips | Strong for reading and handoff, weaker for dense filtering (127/170) | OFL | Cheap | Softer (200–280 ms) | Editorial-print idiom, unproven for video | Medium: warm ramps per theme |
| C. Night Shift: blue-black glass over a blurred live backdrop, scope cyan, Bricolage Grotesque + Onest + Martian Mono, similarity map | Most novel for "find similar", weakest on accessibility, performance and colour neutrality (104/170) | OFL | Expensive: `backdrop-filter` over a virtualised grid plus an extra decode | Expressive (240–400 ms) | Consumer and spatial idiom | High: contrast varies with what is behind the glass |

## Evidence

- Weighted scoring of 16 criteria (8 user stories, then density, accessibility, performance, colour
  neutrality, differentiation, sibling fit, theme parity, build cost): A 162, B 127, C 104. Sensitivity: A still
  leads with differentiation weighted ×3 (178/147/124) and with accessibility and performance weighted 0
  (132/103/92). See `directions.md` §4.
- **Contrast**, computed with the WCAG 2.x formula for every text token on every surface it may sit on: all
  A text tokens are ≥ 4.5:1 in both themes (the worst pair is dark `fg-3` on `bg-pressed` at 4.83:1).
  Control borders are ≥ 3.29:1 and the focus ring is ≥ 10.69:1. Full table in `system.md` §1.1.
- **Font checks** (fontsource 5.3.0 packages inspected with fontTools):
  - Instrument Sans Variable has wght 400–700, wdth 75–100% and `tnum`.
  - JetBrains Mono Variable has wght 100–800, a distinguished zero by default (3 contours) and an x-height
    of 0.55 em.
  - Both are OFL-1.1.
- Research sources: Final Cut Pro range bars and skimming (Apple), Resolve neutral UI and IntelliSearch
  Segments, the Premiere hover-scrub frustrations, grading-suite 18% grey surround (Frame.io, No Film School),
  Figma UI3's reversal of floating panels, and Linear's generated LCH themes. All linked in `research.md`.

## Decision

Adopt **Edge Code** as Metachlorian's design direction, with two borrowings:

1. From **Light Table**: a reading mode for prose (*Why it matched*, descriptions, notes, the handoff note) and
   the contact-sheet strip layout for the *Files* grouping of results.
2. From **Night Shift**: one continuity transition, where the card frame expands into the inspector player
   (180 ms, removed under reduced motion).

Defining choices the builder must follow exactly (specified in `docs/design/system.md` and
`app/src/styles/tokens.css`):

- **Surfaces are exactly neutral** (R = G = B) in both themes. Video sits on a pure-black well (dark) or a
  `#1a1a1a` well (light). The accent never sits behind footage.
- **Accent "Key" magenta**: `#ff5cc8` (dark) / `#a3127a` (light). Used only for selection, primary action,
  the current playhead and the active filter count. Selection is drawn as a 2 px ring **outside** the media.
- **Focus ring** is neutral and maximal-contrast (`#f5f5f5` dark / `#141414` light), 2 px at 2 px offset,
  outside any selection ring.
- **Type:** Instrument Sans Variable (UI and prose; width axis for density) and JetBrains Mono Variable
  (timecode, numbers, slate labels).
- **Dark is the default.** The theme follows `prefers-color-scheme` until the user picks one, and
  `[data-theme]` on `<html>` overrides it.
- **Squarer forms** (4 px radius for controls and cards), hairline dividers, and no cards inside cards.
- **Motion:** 80–180 ms (240 ms for dialogs), standard easing, no bounce. Reduced motion removes all
  non-essential motion and dwell-to-play.

## Consequences

**Easier**
- Editors read the UI as professional software immediately (familiar three-pane geometry, editor keys).
- Footage looks correct: no surround bias, and selection never tints thumbnails.
- One neutral ramp plus one accent gives light/dark parity, high-contrast and forced-colours variants with
  little extra work.
- Solid surfaces keep the grid cheap to render, which protects the 60 fps and < 300 ms budgets.

**Harder**
- Identity rests on details (edge strip, slate labels, Key magenta, typographic width changes). If the builder
  drifts toward generic cards, pill chips and soft shadows, the direction collapses into "another dark
  dashboard". `system.md` lists what not to do.
- Magenta is polarising. It must stay rare (selection and primary only). The Stylelint rule restricts
  `--key*` tokens to listed components.
- Content and marketing leads may find the density austere. The *Comfortable* density setting and reading
  mode address this, and should be validated in usability tests.
- The similarity map (from Night Shift) is deferred, so find-similar is grid-based for now.

## Revisit when

- Usability testing with at least 5 content/marketing leads shows task success < 80% or SUS < 70 on the
  search → select → hand off flow.
- Magenta selection is reported as confusable with any status colour, or it fails a colour-vision simulation
  (protanopia, deuteranopia or tritanopia) against `--status-blocked`.
- Similarity search quality is good enough (offline eval in `eval/`) that a spatial map would beat the grid
  in a task test. Then prototype Night Shift's map as an optional view.
- Cutawan adopts a light theme or changes its accent. Then re-check sibling fit.
