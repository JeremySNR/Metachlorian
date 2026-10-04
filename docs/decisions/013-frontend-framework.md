# 013. Frontend framework, styling, primitives, virtualisation, state and video

- Status: accepted
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context

ADR 001 fixed the delivery model: one React + TypeScript + Vite UI, served by the core as a web app
and wrapped in an Electron 44 shell, with a `capabilities` bridge (`canDragOut`, `canStartLocalCore`,
`canBrowseMdns`) and core-generated H.264 proxies. It named Tailwind 4 only to match Cutawan. This ADR makes
the detailed frontend choices and **amends ADR 001 on styling** (see Decision 2).

Metachlorian's UI is its main differentiator (see `docs/design/research.md` and ADR 014). The frontend must:

- run as an **Electron** desktop app (primary) and as a **web app** served by the same backend, responsive down
  to tablet (768 px);
- scroll **thousands of shot thumbnails** at 60 fps, scrub sprite-sheet previews on hover with no decode, and
  start video preview in **< 300 ms**;
- meet **WCAG 2.2 AA** with full keyboard operation: ARIA grid navigation in a virtualised grid, editor keys
  (J/K/L, I/O, Space), scoped single-key shortcuts (2.1.4) and non-drag alternatives (2.5.7);
- support light and dark themes from one token source (`app/src/styles/tokens.css`);
- be buildable by an autonomous agent and maintainable by open-source contributors.

**Sister app Cutawan** (`/home/user/cutawan`) uses Electron 35, electron-vite 3, Vite 6, React 19, Tailwind 4
(`@theme` in `src/renderer/src/index.css`), Zustand 5 and lucide-react 0.487. It has no headless primitive
library and no virtualisation. Its reusable logic lives in plain TypeScript modules (`lib/format.ts`,
`lib/previewVideo.ts`, which drives preview video imperatively and bypasses React for per-frame updates).
Its components are coupled to its own store and screens.

Versions below were read from the npm registry on 2026-10-04.

## Options considered

### A. UI framework

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **React 19.3 + Vite 8 + TypeScript 7** (React Compiler 1.0) | Best accessibility primitives available (React Aria). Same model as Cutawan. | MIT | Any Chromium (Electron 44) or evergreen browser | VDOM cost is irrelevant once the grid is virtualised and scrub updates bypass React (Cutawan already does this). The Compiler removes most memo boilerplate. | Very high | Largest ecosystem and contributor pool |
| Svelte 5.57 (runes) | Smaller bundles and fine-grained updates. Bits UI 2.19 / Ark UI Svelte 5.24 for primitives, which are less complete for grid/collection a11y. | MIT | Same | Faster DOM updates in micro-benchmarks | High | Good, smaller. No code sharing with Cutawan. |
| SolidJS 1.9 | Fastest fine-grained reactivity. Kobalte 0.13 (pre-1.0), Ark UI Solid. | MIT | Same | Fastest | Medium | Small community. Pre-1.0 primitives. |
| Vue 3.5 | Reka UI 2.10, Ark UI Vue. A good SFC model. | MIT | Same | Comparable to React | High | Large, but no code sharing with Cutawan |

Sources: [Strapi: Svelte vs React 2026](https://strapi.io/blog/svelte-vs-react-comparison),
[SitePoint: React 19 Compiler vs Svelte 5](https://www.sitepoint.com/react-19-compiler-vs-svelte-5-virtual-dom-latency-benchmark/),
[daily.dev: Svelte 5 vs React 2026](https://daily.dev/posts/svelte-5-vs-react-2026-an-honest-comparison-bsbmfirgl).

### B. Styling

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **CSS custom properties (`tokens.css`) + CSS Modules, processed by Lightning CSS** | Tokens are the single source and theme by attribute. Component states map to React Aria `data-*` attributes. No class soup in hot grid cells. | Lightning CSS MPL-2.0 (build-time only) | n/a | Zero runtime. Native cascade. | Very high (platform CSS) | Platform standard |
| Tailwind CSS 4.3 (`@theme`) | Fast to write. Cutawan uses it. v4 emits real CSS variables. | MIT | n/a | Zero runtime | High | Very large |
| vanilla-extract 1.21 | Type-safe tokens at compile time | MIT | n/a | Zero runtime | High | Stable, slower-moving |
| Panda CSS 2.1 | Style props compiled to atomic classes | MIT | n/a | Zero runtime | Medium-high | Chakra team |

Sources: [Tailwind v4 tokens](https://seedflip.co/blog/tailwind-v4-theme-directive),
[PkgPulse: vanilla-extract vs Panda vs Tailwind](https://www.pkgpulse.com/guides/vanilla-extract-vs-panda-css-vs-tailwind-2026),
[OpenReplay: state of CSS-in-JS 2026](https://blog.openreplay.com/state-css-in-js-2026/).

### C. Headless accessible primitives

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **React Aria Components 1.21** (Adobe) | The most rigorous a11y. **GridList with 2-D keyboard layout**, **Virtualizer** (Grid/List/Waterfall/Table layouts) that keeps the focused item in the DOM and adds `aria-rowindex`. Table, Tree, TagGroup, ComboBox, Slider, Menu, Dialog, Toast, DropZone, drag and drop with keyboard alternatives. | Apache-2.0 | n/a | Heavier bundle (tree-shakeable) | High (Adobe Spectrum uses it) | Full-time Adobe team |
| Radix (`radix-ui` 1.6) | Good overlays. **No grid/collection or virtualisation primitives.** | MIT | n/a | Light | High | Slowed after the WorkOS acquisition ([GreatFrontEnd](https://www.greatfrontend.com/blog/top-headless-ui-libraries-for-react-in-2026), [DesignRevision](https://designrevision.com/alternatives/radix-ui)) |
| Base UI 1.8 (MUI) | A modern Radix successor with 35 components. No virtualised grid. | MIT | n/a | Light | 1.0 in Dec 2025 ([InfoQ](https://infoq.com/news/2026/02/baseui-v1-accessible/)) | Full-time MUI team |
| Ark UI 5.39 (Zag state machines) | Cross-framework. Collection support is weaker than React Aria. | MIT | n/a | Light | Medium-high | Chakra team |
| Hand-rolled | Full control | — | — | — | — | High risk of a11y regressions and expensive to maintain |

Sources: [React Aria Virtualizer](https://react-aria.adobe.com/Virtualizer),
[React Aria GridList](https://react-aria.adobe.com/GridList),
[React Spectrum release notes, 5 Mar 2025 (Virtualizer, Toast, Tree)](https://react-spectrum.adobe.com/releases/2025-03-05.html).

### D. Virtualisation

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **React Aria Virtualizer + GridLayout** | Integrated with GridList keyboard nav, selection and focus persistence. `minItemSize`, `maxItemSize`, `minSpace`, `preserveAspectRatio`. | Apache-2.0 | n/a | Good. Must be benchmarked at 10k items. | Stable since 2025 | Adobe |
| **TanStack Virtual 3.14** | Headless and framework-agnostic. Horizontal and grid. Around 6 ms initial render for 100k rows in published comparisons. | MIT | n/a | Excellent | High | Active |
| virtua 0.52 | About 3 kB, zero-config, multi-framework | MIT | n/a | Excellent | Pre-1.0 | One main maintainer |
| react-window 2.3 | Simple | MIT | n/a | Good | High | Slow-moving |
| react-virtuoso 4.18 | Best for grouped lists and tables | MIT | n/a | Good (about 12 ms per 100k) | High | Active |

Sources: [PkgPulse: TanStack Virtual vs react-window vs react-virtuoso](https://www.pkgpulse.com/guides/tanstack-virtual-vs-react-window-vs-react-virtuoso-2026),
[virtua](https://github.com/inokawa/virtua).

### E. State and data

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **TanStack Query 5.104** (server state) + **Zustand 5.0** (UI state) + **TanStack Router 1.170** (typed URL search params) | Clear split: cache and infinite queries, local UI, shareable URL. Zustand matches Cutawan. | MIT | n/a | Excellent | High | Active |
| Jotai 3 | Atom model, fine-grained | MIT | n/a | Excellent | High | Active (diverges from Cutawan) |
| Redux Toolkit / RTK Query | Heavier | MIT | n/a | Good | High | Active |
| React Router 8 | Mature routing. Search params are untyped. | MIT | n/a | Good | High | Active |

### F. Video

| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **Native `<video>` + faststart MP4 proxies + WebP sprite sheets (WebVTT `#xywh` map) + a pooled set of 4 preview elements** | Smallest moving parts. Hardware decode. Frame-accurate readout via `requestVideoFrameCallback`. | n/a | H.264 hardware decode on every target | Scrub needs no decode. Preview start is dominated by first-byte time. | Platform | Platform |
| hls.js 1.7 | ABR for long assets over WAN | Apache-2.0 | MSE | Adds segment latency (startup is slower than a faststart MP4 on LAN) | High | Active |
| media-chrome 4.19 | Web-component player controls | MIT | — | — | High | Mux |
| WebCodecs | Frame-exact decode for the filmstrip | n/a | — | Best, but complex | Platform | — |

Sources: [WebVTT sprite thumbnails with ffmpeg](https://dev.to/masonwritescode/build-scrub-bar-thumbnail-previews-with-ffmpeg-and-a-webvtt-sprite-3ei2),
[ffmpeg faststart](https://ffmpeg-cookbook.com/en/articles/ffmpeg-faststart-web-playback/),
[web.dev: requestVideoFrameCallback](https://web.dev/articles/requestvideoframecallback-rvfc),
[Chromium WebMediaPlayer limit](https://groups.google.com/a/chromium.org/g/media-dev/c/wEUYR7BvdZI/m/R-8X1EdiBAAJ).

## Evidence

- **Registry versions (2026-10-04):** react 19.3.0, vite 8.3.2, typescript 7.0.2, electron 44.5.1,
  electron-vite 5.0.0, react-aria-components 1.21.1, @tanstack/react-virtual 3.14.13, virtua 0.52.10,
  react-window 2.3.3, react-virtuoso 4.18.16, @tanstack/react-query 5.104.1, zustand 5.0.15,
  @tanstack/react-router 1.170.41, hls.js 1.7.3, media-chrome 4.19.3, tailwindcss 4.3.3,
  @vanilla-extract/css 1.21.2, @pandacss/dev 2.1.1, radix-ui 1.6.7, @base-ui/react 1.8.0, @ark-ui/react 5.39.2,
  lucide-react 1.51.0 (ISC), lightningcss 1.33.0, svelte 5.57.1, solid-js 1.9.15, vue 3.5.43, bits-ui 2.19.5,
  @kobalte/core 0.13.14, reka-ui 2.10.5.
- **No benchmarks have been run yet.** The following are acceptance gates the builder must add under
  `bench/` before the grid ships:
  1. `bench/grid-scroll`: 10,000 shot cards at M size (232 px), fling-scrolled for 10 s. p95 frame time
     ≤ 16.7 ms and no long tasks over 50 ms, on Electron (Apple M1 8 GB and an Intel i5 laptop with iGPU)
     and in Chrome stable.
  2. `bench/preview-start`: from `Space` (or hover dwell end) to the first painted frame
     (`requestVideoFrameCallback`), p95 ≤ 300 ms for local proxies in Electron and ≤ 300 ms on LAN web.
  3. `bench/scrub`: sprite-frame update on `pointermove` ≤ 1 frame (16.7 ms) p95.
  4. Memory: ≤ 600 MB renderer heap after scrolling 10,000 results.
- The design system's performance budget is in `docs/design/system.md` §6.

## Decision

1. **React 19 + TypeScript + Vite**, with **electron-vite 5** for the desktop build and plain Vite for the web
   build from the same `app/src`. Enable the **React Compiler**. Start on current majors (Electron 44,
   Vite 8), not Cutawan's pinned versions.
2. **Styling: `app/src/styles/tokens.css` (custom properties) + CSS Modules** (`Component.module.css`), with
   Vite's `css.transformer: 'lightningcss'` for nesting and minification. No Tailwind, CSS-in-JS or utility
   framework in Metachlorian. **This supersedes the "Tailwind 4" clause of ADR 001 Decision 2.** Every other
   part of ADR 001 stands. Reasons:
   - tokens must be the only source of colour, spacing and motion, and an `@theme` default palette invites
     drift toward the generic look the brief forbids;
   - component states are styled from React Aria's `data-*` attributes (`[data-focus-visible]`,
     `[data-selected]`, `[data-hovered]`, `[data-pressed]`, `[data-disabled]`, `[data-dragging]`), which read
     cleanly in CSS Modules;
   - grid cells render thousands of times, and short stable class names keep DOM and diff cost low.

   **Cutawan bridge:** Cutawan can adopt the same tokens with
   `@import "…/tokens.css"; @theme inline { --color-surface-950: var(--bg-canvas); … }` without changing its
   component code.
3. **Primitives: React Aria Components** for every interactive primitive: Button, ToggleButton,
   ToggleButtonGroup (segmented control), SearchField and ComboBox (command input), TagGroup (chips),
   CheckboxGroup, RadioGroup, Switch, Slider (ranges), NumberField, **GridList** (results grid,
   `layout="grid"`), **Table** (admin, signals, ingest), Tree (library sidebar), Menu, Popover, Dialog and
   Modal, Tooltip, Toast, Tabs, Disclosure, DropZone and FileTrigger (ingest). If an API is still marked
   `UNSTABLE_`, wrap it behind our own component so the call sites never change.

   **Hand-rolled** (on React Aria hooks: `useMove`, `useSlider`, `useFocusRing`, `useKeyboard`): the
   filmstrip/timeline, the scrub preview, player transport, the confidence meter (`role="meter"`) and the
   match-strength rail.
4. **Virtualisation:** React Aria **Virtualizer + GridLayout** for the results grid and every React Aria
   collection (it keeps focus and `aria-rowindex` correct). Use **TanStack Virtual** for surfaces outside React
   Aria collections: the horizontal filmstrip thumbnails, the ingest log, and the Library overview heatmap rows.
   **Fallback:** if `bench/grid-scroll` fails with Virtualizer, switch the grid to TanStack Virtual plus a
   hand-rolled APG grid that follows `system.md` §3.4 exactly (roving tabindex, `aria-rowcount`,
   `aria-rowindex`, focused-row pinning).
5. **State:** TanStack Query for server state (search as `useInfiniteQuery` with 120-item pages, shot detail
   prefetched on hover intent and focus). Zustand for UI state (selection `Set<ShotId>`, active collection,
   panel sizes, player, shortcut map). **TanStack Router** with typed search params for query, filters, view,
   size, sort and the open shot, so every search is a shareable URL in web mode and is restored on relaunch
   in Electron.
6. **Video:** native `<video>` only.
   - Poster: WebP 480 × 270.
   - **Sprite** per shot: WebP, 24 frames of 240 × 135 in a 6 × 4 grid, plus a WebVTT `#xywh` map. Loaded with
     the poster for visible rows, 1 row of overscan.
   - **Preview MP4** per shot: H.264 High, 854 × 480, about 1.2 Mbit/s, `+faststart`, 0.5 s GOP, muted, centred
     clip of at most 10 s.
   - **Player proxy** per asset: H.264 (HEVC where hardware-decodable) 1280 × 720, 1 s GOP, AAC,
     `+faststart`. Served with HTTP Range through an Electron `protocol.handle('mc-media', …)` handler, and over
     HTTP in web mode.
   - Pool of **4** preview `<video>` elements and 1 player element. Use `fastSeek()` while dragging and an
     exact `currentTime` on release.
   - `hls.js` only when the web app streams an asset over 10 minutes across a WAN, behind a feature flag.
   - Per-frame updates (scrub frame, timecode readout, playhead) are **imperative** through refs, following
     Cutawan's `previewVideo.ts` pattern, and never go through React state.
7. **Icons:** `lucide-react` (ISC), the same as Cutawan. **Fonts:** fontsource variable packages bundled
   locally, never a font CDN (the app is self-hosted and must work offline):
   `@fontsource-variable/instrument-sans` (import `wdth.css`) and `@fontsource-variable/jetbrains-mono`.
8. **Code sharing with Cutawan** is at the **module level, not the component level**, and **without a shared
   monorepo** (ADR 001 rejected one). Metachlorian keeps a small workspace package `packages/media-kit`
   (plain TypeScript, no React, MIT-compatible), containing:
   - timecode parse/format (SMPTE, drop-frame);
   - the preview-video pool;
   - TypeScript types for the handoff manifest, **generated** from
     `docs/integration/cutawan-package.schema.json` (ADR 012) with `json-schema-to-typescript`.

   It is published to npm when Cutawan wants it. Until then Cutawan keeps its hand-written checks, as ADR 012
   specifies. Components are not shared, because the products have different densities and stores.

## Consequences

**Easier**
- Grid accessibility, typeahead, multi-select, drag and drop with keyboard alternatives, and focus
  persistence under virtualisation come from React Aria instead of custom code.
- Themes, density, reduced motion and high contrast are attribute switches on `<html>` over a single
  token file.
- Contributors who know React and Zustand from Cutawan are productive immediately.
- Shareable search URLs fall out of typed router state.

**Harder**
- React Aria's collection API (`items`, `id`, render props) has a learning curve, and its bundle is larger
  than Radix's. Import per component and check `vite build --report` (budget: ≤ 250 kB gzip for the initial
  route).
- No Tailwind means writing CSS. Every module must use tokens only. Add a Stylelint rule that rejects raw hex,
  px font sizes and unlisted durations outside `tokens.css`.
- Generating ingest artefacts (poster, sprite, preview MP4, proxy) costs disk and CPU (about 5–8% of source
  size for proxies). The ingest pipeline owns that cost, and the UI depends on it.
- Two virtualisers in one codebase. The split is by surface (React Aria collections vs custom surfaces) and
  is documented in `system.md`.
- Desktop-only affordances (drag-out to an NLE, *Reveal in Finder/Explorer*, start a local core) must check
  ADR 001's `capabilities` bridge and degrade in the web build ("Copy path", "Download proxy"). Every such
  control is specified with its web fallback in `system.md`.

## Revisit when

- `bench/grid-scroll` or `bench/preview-start` misses its gate on the reference hardware. Switch the grid to
  TanStack Virtual with a hand-rolled APG grid first, before reconsidering the framework.
- React Aria Components goes six months without a release, or a major version breaks GridList or
  Virtualizer.
- Cutawan migrates off React, or both apps merge into one shell. Then revisit shared components and Tailwind.
- WebCodecs-based thumbnailing becomes needed for frame-exact filmstrips on long assets.
- Web deployments routinely stream over WAN to remote editors. Then promote hls.js from flag to default for
  long assets.
