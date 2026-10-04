# Edge Code: the Metachlorian design system

- Status: accepted (ADR 014). This is the build specification, so implement it exactly.
- Date: 2026-10-04
- Tokens: `app/src/styles/tokens.css` (the only place raw values may appear)
- Stack: React 19, React Aria Components, CSS Modules, lucide-react (ADR 013)

> **Edge Code** in one line: footage is the only colour. Everything Metachlorian knows about a shot is printed
> beside it, small and exact, like the edge codes on film stock.

## 0. Principles and hard rules

1. **Neutral surfaces.** Every surface token is R = G = B. Never tint a surface, and never put the accent
   behind footage.
2. **One accent, rarely.** `--key` (magenta) is allowed **only** for:
   - selection (ring, check, row tint);
   - the single primary button in a view;
   - the playhead;
   - the active-filter count;
   - the current item in a progress or step sequence.

   Anything else needs a design review.
3. **Status = icon + word + colour.** Never colour alone.
4. **Type does the hierarchy.** Use weight, width (`font-stretch`), size and mono vs sans. Use hairlines, not
   boxes. Never put a card inside a card.
5. **The shot is the unit.** Wherever a shot appears, its timecode is visible or one keystroke away.
6. **Evidence over magic.** Every AI-derived value shows its source and confidence, and any human change is
   marked.
7. **Instant or honest.** Respond in under 100 ms, or show real progress after 400 ms. No shimmer and no
   decorative spinners.

**Don't** (these turn Edge Code into a generic dashboard):
- pill-shaped chips;
- soft drop shadows on cards;
- gradients;
- coloured icon backgrounds;
- rounded-xl (12 px+) corners on controls;
- emoji;
- KPI "stat cards";
- avatars stacked as decoration;
- `backdrop-filter` inside any scrolling region;
- skeleton shimmer;
- toasts for things that are already visible;
- Title Case labels;
- the word "AI-powered".

---

## 1. Tokens

All tokens are CSS custom properties on `:root` in `app/src/styles/tokens.css`. Colours use `light-dark()`, so
**one declaration per token** serves both themes. The theme is chosen by `color-scheme`:

| Situation | Result |
|---|---|
| No `data-theme` on `<html>` | Follows the OS (`prefers-color-scheme`). If the OS reports no preference, dark. |
| `<html data-theme="light">` | Light |
| `<html data-theme="dark">` | Dark |
| Any subtree with `color-scheme: dark` (for example, player chrome) | Tokens inside it resolve dark, even in the light theme |

In Electron, keep `nativeTheme.themeSource` in sync (`'system' | 'light' | 'dark'`). The user setting lives in
*Settings → Appearance → Theme: System / Light / Dark*.

`light-dark()` needs Chromium 123+, Firefox 120+ or Safari 17.5+. Electron 44 and every evergreen browser
qualify.

### 1.1 Colour

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg-canvas` | `#141414` | `#e8e8e8` | App background, results well, filmstrip lane |
| `--bg-panel` | `#1a1a1a` | `#f4f4f4` | Top bar, filter rail, inspector, selection bar |
| `--bg-raised` | `#212121` | `#ffffff` | Inputs, secondary buttons, table header |
| `--bg-overlay` | `#242424` | `#ffffff` | Menus, popovers, dialogs, toasts |
| `--bg-hover` | `#2a2a2a` | `#e0e0e0` | Hover on rows, cards' edge strip, quiet buttons |
| `--bg-pressed` | `#333333` | `#d6d6d6` | Pressed, current row (not selection), selected segment |
| `--bg-selected` | `#3a1a30` | `#f7dcef` | Selected rows in lists and tables (Key tint) |
| `--bg-well` | `#000000` | `#1a1a1a` | Video player well |
| `--bg-letterbox` | `#0d0d0d` | `#cfcfcf` | Thumbnail letterbox and pillarbox bars, image placeholders |
| `--bg-inverse` | `#ececec` | `#141414` | Human marker chip, tooltip |
| `--fg-1` | `#ececec` | `#141414` | Primary text, icons |
| `--fg-2` | `#b4b4b4` | `#434343` | Secondary text, meter fill |
| `--fg-3` | `#a0a0a0` | `#545454` | Tertiary text, slate labels, counts, leading timecode zeros |
| `--fg-disabled` | `#5e5e5e` | `#a3a3a3` | Disabled text (exempt from 1.4.3; always paired with `aria-disabled`) |
| `--fg-inverse` | `#141414` | `#f4f4f4` | Text on `--bg-inverse` |
| `--fg-on-key` | `#1a0012` | `#ffffff` | Text and icons on `--key` |
| `--fg-on-scrim` | `#ffffff` | `#ffffff` | Text on footage (always over `--scrim`) |
| `--fg-on-danger` | `#1a0000` | `#ffffff` | Text on a filled `--status-blocked` button |
| `--border-subtle` | `#262626` | `#e3e3e3` | Decorative hairlines between rows and sections |
| `--border-default` | `#333333` | `#d4d4d4` | Panel edges, popover outline |
| `--border-control` | `#828282` | `#6e6e6e` | Input, checkbox, chip and secondary button outlines (1.4.11) |
| `--border-strong` | `#a0a0a0` | `#545454` | Hover on controls |
| `--key` | `#ff5cc8` | `#a3127a` | Accent (see §0 rule 2) |
| `--key-hover` | `#ff85d6` | `#8a0c66` | Primary button hover |
| `--key-pressed` | `#e84fb5` | `#730955` | Primary button pressed |
| `--status-cleared` / `-bg` | `#4cc38a` / `#14271d` | `#11663e` / `#dcf1e5` | Rights cleared, success |
| `--status-caution` / `-bg` | `#f0b429` / `#2b2210` | `#754c00` / `#f8ebcf` | Restricted, expiring, "leaves this machine" |
| `--status-blocked` / `-bg` | `#ff6b6b` / `#2e1616` | `#ad1f28` / `#f9dfe0` | Blocked, expired, errors, destructive |
| `--status-info` / `-bg` | `#6cb6ff` / `#142233` | `#1a52a6` / `#dde8f8` | Processing, informational |
| `--focus-ring` | `#f5f5f5` | `#141414` | Focus indicator |
| `--scrim` | `rgb(0 0 0 / 0.72)` | same | Behind any text or icon drawn over footage |
| `--viz-0` … `--viz-5` | `#262626 #3d3d3d #5c5c5c #858585 #b4b4b4 #ececec` | `#e0e0e0 #c4c4c4 #9e9e9e #737373 #4a4a4a #1f1f1f` | Neutral sequential ramp (coverage heatmap). Gaps (0) are also hatched. |

#### Verified contrast (WCAG 2.x relative luminance)

Text tokens against **every** surface they may sit on. The minimum is 4.5:1, and the lowest cell is shown in bold.

| Dark | canvas `#141414` | panel `#1a1a1a` | raised `#212121` | hover `#2a2a2a` | pressed `#333333` | overlay `#242424` | selected `#3a1a30` |
|---|---|---|---|---|---|---|---|
| `--fg-1` `#ececec` | 15.59 | 14.73 | 13.63 | 12.15 | 10.69 | 13.14 | 12.97 |
| `--fg-2` `#b4b4b4` | 8.89 | 8.39 | 7.77 | 6.92 | 6.09 | 7.49 | 7.39 |
| `--fg-3` `#a0a0a0` | 7.04 | 6.66 | 6.16 | 5.49 | **4.83** | 5.94 | 5.86 |
| `--key` `#ff5cc8` (as text) | 6.68 | 6.31 | 5.84 | 5.21 | **4.58** | 5.63 | 5.56 |
| `--status-cleared` `#4cc38a` | 8.32 | 7.86 | 7.27 | 6.48 | 5.70 | 7.01 | 6.92 |
| `--status-caution` `#f0b429` | 9.88 | 9.34 | 8.64 | 7.70 | 6.78 | 8.33 | 8.22 |
| `--status-blocked` `#ff6b6b` | 6.64 | 6.27 | 5.80 | 5.17 | **4.55** | 5.59 | 5.52 |
| `--status-info` `#6cb6ff` | 8.57 | 8.10 | 7.49 | 6.68 | 5.88 | 7.22 | 7.13 |
| `--border-control` `#828282` (3:1 needed) | 4.79 | 4.53 | 4.19 | 3.74 | **3.29** | 4.04 | 3.99 |
| `--focus-ring` `#f5f5f5` (3:1 needed) | 16.90 | 15.96 | 14.77 | 13.17 | **11.59** | 14.24 | 14.06 |

| Light | canvas `#e8e8e8` | panel `#f4f4f4` | raised `#ffffff` | hover `#e0e0e0` | pressed `#d6d6d6` | overlay `#ffffff` | selected `#f7dcef` |
|---|---|---|---|---|---|---|---|
| `--fg-1` `#141414` | 15.04 | 16.75 | 18.42 | 13.96 | 12.68 | 18.42 | 14.42 |
| `--fg-2` `#434343` | 8.07 | 9.00 | 9.89 | 7.49 | 6.81 | 9.89 | 7.74 |
| `--fg-3` `#545454` | 6.18 | 6.89 | 7.57 | 5.74 | **5.21** | 7.57 | 5.93 |
| `--key` `#a3127a` (as text) | 5.86 | 6.53 | 7.18 | 5.44 | **4.94** | 7.18 | 5.62 |
| `--status-cleared` `#11663e` | 5.72 | 6.38 | 7.01 | 5.31 | **4.83** | 7.01 | 5.49 |
| `--status-caution` `#754c00` | 6.14 | 6.84 | 7.53 | 5.70 | 5.18 | 7.53 | 5.89 |
| `--status-blocked` `#ad1f28` | 5.71 | 6.36 | 6.99 | 5.30 | **4.81** | 6.99 | 5.47 |
| `--status-info` `#1a52a6` | 6.12 | 6.82 | 7.50 | 5.68 | 5.16 | 7.50 | 5.87 |
| `--border-control` `#6e6e6e` (3:1 needed) | 4.16 | 4.64 | 5.10 | 3.86 | **3.51** | 5.10 | 3.99 |
| `--focus-ring` `#141414` (3:1 needed) | 15.04 | 16.75 | 18.42 | 13.96 | **12.68** | 18.42 | 14.42 |

Other verified pairs:

| Pair | Dark | Light |
|---|---|---|
| `--fg-on-key` on `--key` / `--key-hover` / `--key-pressed` | 7.24 / 9.10 / 5.91 | 7.18 / 9.03 / 11.06 |
| `--fg-on-danger` on `--status-blocked` | 7.25 | 6.99 |
| Status text on its own `-bg` (cleared / caution / blocked / info) | 7.09 / 8.41 / 6.09 / 7.48 | 5.93 / 6.37 / 5.55 / 6.06 |
| `--fg-inverse` on `--bg-inverse` (human chip, tooltip) | 15.59 | 16.75 |
| `--fg-on-scrim` on `--scrim` composited over pure white footage (worst case) | 9.29 | 9.29 |
| `--key` selection ring against `--bg-canvas` (non-text, 3:1) | 6.68 | 5.86 |
| `--fg-2` meter fill against track `--viz-1` / against `--bg-raised` | 5.24 / 7.77 | 5.67 / 9.89 |
| `--fg-1` on `--bg-letterbox` | 16.45 | 11.82 |

**Colour-vision check** (Machado 2009 simulation at full severity, CIE ΔE76 between `--key` and each status
colour). The lowest values are dark *key vs blocked* under tritanopia at 14.4, *key vs info* under protanopia
at 17.4 (dark) and 16.8 (light). All exceed 10, so they stay distinguishable. Status is also always icon plus
word, so this is belt and braces.

**Reproduce:** this is the WCAG relative-luminance formula. Run it in CI as `scripts/check-contrast.ts` against
the token file.
```text
lin(c) = c/12.92 if c ≤ 0.04045 else ((c+0.055)/1.055)^2.4      (c = channel/255)
L = 0.2126 R + 0.7152 G + 0.0722 B                               (linearised)
ratio = (L_hi + 0.05) / (L_lo + 0.05)
```

**Rules**
- Text over footage always sits on `--scrim` (a chip with 4 px horizontal padding), never with a text shadow.
- `--fg-3` is the lowest text tier. Never use opacity to dim text.
- `--fg-disabled` is only for disabled controls, which are also `aria-disabled` and stay focusable when they
  explain why ("Send to Cutawan, unavailable: 2 selected shots are blocked").

### 1.2 Typography

| Family token | Font | Package | Axes |
|---|---|---|---|
| `--font-sans` | **Instrument Sans Variable** | `@fontsource-variable/instrument-sans` (import `wdth.css`) | wght 400–700, wdth 75–100% |
| `--font-mono` | **JetBrains Mono Variable** | `@fontsource-variable/jetbrains-mono` (import `index.css`) | wght 100–800 |

Both are OFL-1.1 and bundled locally (no CDN). Fallbacks are `ui-sans-serif, system-ui, "Segoe UI", Roboto,
sans-serif` and `ui-monospace, "SF Mono", Menlo, Consolas, monospace`.

**Scale** (rem, root 16 px; *Settings → Appearance → Text size* sets `html { font-size }` to 100%, 112.5% or
125%):

| Token | Size / line | Default use |
|---|---|---|
| `--text-2xs` | 11 / 16 | **Mono only.** Slate labels (uppercase, `--tracking-label`), ruler ticks, kbd hints |
| `--text-xs` | 12 / 16 | Edge strip timecode, counts, chip text, table secondary |
| `--text-sm` | 13 / 18 | **Default UI text**: rail rows, menu items, buttons, card titles |
| `--text-md` | 14 / 22 | Prose (descriptions, *Why it matched*, notes), table body, dialog body |
| `--text-lg` | 16 / 24 | Search input, panel titles |
| `--text-xl` | 20 / 26 | Page titles (Shot detail, Asset view), player timecode readout (mono) |
| `--text-2xl` | 26 / 32 | Empty-state headline, Library overview figures |
| `--text-3xl` | 36 / 42 | First-run search prompt only |

**Roles** (each a CSS Modules composition defined in `app/src/styles/type.module.css`):

| Role | Family | Size | Weight | Width | Other |
|---|---|---|---|---|---|
| `slate` | mono | 2xs | 500 | — | uppercase, `letter-spacing: var(--tracking-label)`, `--fg-3` |
| `ui` | sans | sm | 400 | 100% | — |
| `ui-strong` | sans | sm | 600 | 100% | — |
| `card-title` | sans | sm | 500 | **87.5%** | one line, ellipsis |
| `prose` | sans | md | 400 | 100% | `max-inline-size: var(--measure-prose)` (64ch) |
| `title` | sans | xl | 600 | 100% | `letter-spacing: var(--tracking-tight)` |
| `timecode` | mono | xs/sm/xl | 400 (500 at xl) | — | `font-variant-numeric: tabular-nums`, `font-feature-settings: "calt" 0` |
| `numeric` | sans | any | any | — | `font-variant-numeric: tabular-nums` (counts, sizes) |

Mono digits are already fixed-width, and JetBrains Mono's zero is distinguished by default. Disable `calt` so
sequences such as `->` or `::` never ligate in data.

### 1.3 Spacing (4 px base)

`--space-0` 0 · `--space-0_5` 2 · `--space-1` 4 · `--space-1_5` 6 · `--space-2` 8 · `--space-3` 12 ·
`--space-4` 16 · `--space-5` 20 · `--space-6` 24 · `--space-8` 32 · `--space-10` 40 · `--space-12` 48 ·
`--space-16` 64 (px).

Panel inner padding is `--space-4`. The gap between rail rows is 0 (row height carries the rhythm). Section
gaps are `--space-6`. Dialog padding is `--space-6`. Grid gutter is `--thumb-gap` (12, or 8 in compact).

### 1.4 Sizes

| Token | Value | Use |
|---|---|---|
| `--control-sm` / `-md` / `-lg` | 24 / 32 / 40 px | Icon buttons in dense rows / default controls / search input |
| `--row-height` | 28 px (compact 24, comfortable 36) | Rail rows, menu items, list rows |
| `--table-row-height` | 36 px (compact 32, comfortable 44) | Tables |
| `--target-min` | 24 px | Smallest pointer target (2.5.8) |
| `--target-coarse` | 44 px | Every target under `@media (pointer: coarse)` |
| `--icon-sm` / `-md` / `-lg` | 14 / 16 / 20 px | In chips and badges / default / toolbar |
| `--topbar-height` | 52 px | — |
| `--selectionbar-height` | 48 px | — |
| `--rail-width` | 264 px (min 220, max 360, collapsed 48) | Filter rail |
| `--inspector-width` | 384 px (min 320, max 560) | Inspector |
| `--thumb-s` / `-m` / `-l` | 168 / 232 / 320 px | Minimum card width per size |
| `--thumb-gap` | 12 px (compact 8) | Grid gutter |
| `--filmstrip-height` | 96 px | Asset timeline (lanes in §3.11) |
| `--measure-prose` | 64ch | Prose line length |

### 1.5 Radii

`--radius-none` 0 · `--radius-xs` 2 px (meter segments, kbd) · `--radius-sm` **4 px (default: buttons,
inputs, chips, frames, cards)** · `--radius-md` 6 px (menus, popovers, toasts) · `--radius-lg` 8 px (dialogs)
· `--radius-full` (switch track and avatar only).

### 1.6 Borders

Hairlines are 1 px solid `--border-subtle` (rows) or `--border-default` (panel edges). Controls get 1 px
`--border-control`. On high-DPI screens do **not** use 0.5 px, because it disappears at some zoom levels.

### 1.7 Elevation

Elevation exists only for things that float. Panels are flat and separated by hairlines.

| Token | Value | Use |
|---|---|---|
| `--shadow-popover` | outline in `--border-default` + `0 8px 24px` at 50% black (dark) / 12% (light) | Menus, popovers, tooltips, hover preview |
| `--shadow-dialog` | outline + `0 24px 64px` at 60% / 18% | Dialogs, sheets, command menu |
| `--shadow-drag` | outline in `--key` + `0 12px 32px` at 50% / 16% | Drag ghost |

### 1.8 Z-index

`--z-base` 0 · `--z-raised` 1 · `--z-sticky` 10 (sticky headers, rail section headers) · `--z-panel` 20
(rails, inspector overlays on laptop) · `--z-topbar` 30 · `--z-preview` 40 (hover preview popover) ·
`--z-popover` 50 · `--z-dialog` 60 · `--z-toast` 70 · `--z-tooltip` 80 · `--z-drag` 90.

### 1.9 Motion tokens

| Token | Value | Use |
|---|---|---|
| `--dur-0` | 0 ms | — |
| `--dur-1` | 80 ms | Hover colour, focus ring appear |
| `--dur-2` | 120 ms | Press, chip add/remove, selection ring, toggles |
| `--dur-3` | 180 ms | Popover and menu, panel collapse, card → inspector flight |
| `--dur-4` | 240 ms | Dialog and sheet enter |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | Most transitions |
| `--ease-enter` | `cubic-bezier(0, 0, 0, 1)` | Things appearing |
| `--ease-exit` | `cubic-bezier(0.3, 0, 1, 1)` | Things leaving (use `--dur-2`) |
| `--delay-hover-intent` | 150 ms | Start prefetching the preview MP4 |
| `--delay-preview-dwell` | 400 ms | Start playing the preview (if enabled) |
| `--delay-tooltip` | 500 ms | Tooltip open (0 ms once one tooltip is open, for 1 s) |
| `--delay-progress` | 400 ms | Show progress indicators only after this |
| `--toast-duration` | 6000 ms | Auto-dismiss for non-error toasts |

Under reduced motion every `--dur-*` becomes 0 ms and `--preview-autoplay` becomes `0` (§4).

### 1.10 Focus and selection rings

- **Focus:** `outline: var(--focus-ring-width) solid var(--focus-ring); outline-offset: var(--focus-ring-offset);`
  (2 px, 2 px). Show it only on `[data-focus-visible]` (React Aria) or `:focus-visible`. It meets 2.4.7,
  2.4.11 and 2.4.13 (2 px perimeter, ≥ 11:1 against every surface).
- **Selection** (cards): `box-shadow: 0 0 0 var(--select-ring-gap) var(--bg-canvas), 0 0 0 calc(var(--select-ring-gap) + var(--select-ring-width)) var(--key);`
  on the frame. That is a 2 px canvas gap, then 2 px of Key, drawn **outside** the footage. The card
  container then takes the focus ring at a 2 px offset, so both rings stack: frame | gap | key | gap | focus.
- **Selection** (rows): `--bg-selected` plus a 2 px inset bar in `--key` on the leading edge, plus a checked
  checkbox.
- Sticky top bar, sticky headers and toasts set `scroll-padding-block` on the scroller (top: header height +
  8 px; bottom: selection bar + toast stack). The focused item is never hidden (2.4.11).

### 1.11 Theming attributes on `<html>`

| Attribute | Values | Effect |
|---|---|---|
| `data-theme` | (absent) / `light` / `dark` | Colour scheme (§1) |
| `data-density` | `compact` / (absent = default) / `comfortable` | Row and control heights, grid gap |
| `data-motion` | (absent = follow OS) / `reduced` / `full` | Overrides `prefers-reduced-motion` |
| `data-contrast` | (absent = follow OS) / `more` | Raises `--fg-2`/`--fg-3` to `--fg-1`, borders to `--border-strong`, rings to 3 px |
| `data-scrub` | `on` / `off` | Hover scrub on cards (JS reads it; CSS hides the scrub bar) |

`@media (forced-colors: active)` maps focus and selection to `Highlight`, borders to `CanvasText` and status
to `CanvasText` (icons and words still carry the meaning).

---

## 2. Layout grid and breakpoints

### 2.1 App shell (desktop)

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR 52: logo · nav · SEARCH (flex, max 760) · egress · help · settings       │
├──────────────┬───────────────────────────────────────────────┬───────────────────┤
│ FILTER RAIL  │ RESULTS HEADER 40                             │ INSPECTOR 384     │
│ 264          │ count · grouping · view · size · sort         │ (320–560,         │
│ (220–360,    │───────────────────────────────────────────────│  collapsible)     │
│  collapsible │ RESULTS (virtualised grid)                    │                   │
│  to 48)      │                                    match rail │                   │
├──────────────┴───────────────────────────────────────────────┴───────────────────┤
│ SELECTION BAR 48 (only when ≥ 1 selected)                                        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- Panels are **fixed and resizable** with React Aria-based splitters (`role="separator"`,
  `aria-valuenow`, arrow keys resize by 16 px, `Enter` collapses or expands). Each splitter also has a
  collapse button (2.5.7). Sizes persist per user.
- On macOS Electron the top bar is the title bar (`titleBarStyle: 'hiddenInset'`, 84 px left inset), as in
  Cutawan. It may use `backdrop-filter: blur(20px)` over `--bg-panel` at 80% opacity, **only in the top bar**.
- Landmarks: `header` (top bar), `nav` (section nav), `search` (search form), `aside`
  aria-label="Filters", `main` (results), `aside` aria-label="Shot details" (inspector), and a `region`
  aria-label="Selection" for the selection bar. `F6` / `Shift+F6` cycle them.

### 2.2 Breakpoints

| Name | Range | Rail | Inspector | Grid (M) | Notes |
|---|---|---|---|---|---|
| **Wide** | ≥ 1680 | open 264 | open 400 | 5–7 columns | — |
| **Desktop** | 1280–1679 | open 264 | open 384 | 3–5 columns | Primary target |
| **Laptop** | 1024–1279 | open 240 | **overlay sheet** (384, `--z-panel`, `--shadow-dialog`), or pinned by user | 3–4 | Opening a shot opens the sheet. `Esc` closes it. |
| **Tablet** | 768–1023 | **drawer** (modal, 320, from left) with a **Show N shots** batch-apply footer | full-height sheet from right, `min(480px, 100%)` | 2–3 | `pointer: coarse` → 44 px targets. Hover scrub off. A play button on the card. |
| Narrow | < 768 | drawer | full screen | 1–2 | Supported, not optimised (stacked) |

Media queries use `width` ranges (`@media (1024px <= width < 1280px)`), not device names. Container queries
(`@container results (width < 600px)`) drive the card's internal layout so cards adapt to panel resizing too.

### 2.3 Results grid geometry

React Aria `GridLayout`:
- `minItemSize: { width: var(--thumb-*), height: frame + 44 }`;
- `maxItemSize.width = minItemSize.width × 1.35`;
- `minSpace = { --thumb-gap, --thumb-gap + 4 }`;
- `preserveAspectRatio: true`.

Cards stretch to fill the row up to their max, and leftover space goes to the margins (no ragged right edge).
Overscan is 2 rows.

### 2.4 Page grid (Settings, Rights, Library overview, Ingest)

A 12-column grid with `max-inline-size: 1200px`, 24 px gutters and 32 px page padding (16 px on tablet).
Forms are 6 columns wide (≈ 560 px). Tables span 12.

---

## 3. Components

Each entry gives anatomy, sizes, states, behaviour, keyboard, ARIA and copy. "RAC" means React Aria
Components. States always include: default, hover, focus-visible, pressed, disabled, plus any listed.

### 3.1 Button and icon button (RAC `Button`, `ToggleButton`)

| Variant | Fill | Text | Border | Use |
|---|---|---|---|---|
| `primary` | `--key` (hover `--key-hover`, pressed `--key-pressed`) | `--fg-on-key`, 600 | none | **At most one per view** |
| `secondary` | `--bg-raised` (hover `--bg-hover`) | `--fg-1`, 500 | `--border-control` (hover `--border-strong`) | Default |
| `quiet` | transparent (hover `--bg-hover`, pressed `--bg-pressed`) | `--fg-2` → `--fg-1` on hover | none | Toolbars, rows |
| `danger` | transparent → `--status-blocked-bg` | `--status-blocked` | `--status-blocked` | Destructive. Filled (`--status-blocked` fill with `--fg-on-danger` text) only inside confirm dialogs |

Sizes: `sm` 24 (icon or 12 px label), `md` 32 (13 px label, 12 px horizontal padding), `lg` 40. Icon plus label
gap is 6 px. Icon buttons are square and **always** have `aria-label` plus a tooltip that shows the label and
shortcut. Loading: the label stays, a 14 px `loader-circle` replaces the icon after `--delay-progress`, and
`aria-busy`. Disabled: `--fg-disabled`, no border change, `aria-disabled` (still focusable if it has a reason
tooltip).

### 3.2 Search bar (command input)

**Anatomy:** `search` landmark → RAC `ComboBox`-pattern input (`--control-lg`, `--bg-raised`, 1 px
`--border-control`, 4 px radius) → leading `search` icon (16) → input text `--text-lg` → trailing:
- clear button (`x`, 24) when there is text;
- a `kbd` hint `⌘K` / `Ctrl K` (mono 2xs, `--fg-3`, 1 px `--border-subtle`, 2 px radius).

Below the input is the **parsed chip row** (§3.3) in a RAC `TagGroup`, 28 px tall, scrolling horizontally
with fade masks.

**Behaviour**
- Typing parses locally (≤ 50 ms) into chips plus a free-text residue. The server parse refines the chips
  on submit.
- **Suggestions popover** (opens after 1 character, 150 ms debounce) has sections in this order: *Saved
  searches*, *Tags*, *Places*, *People*, *Collections*, *Recent*. Each row shows icon, label, slate label and a
  count. Up to 8 per section, 24 total.
- `↓`/`↑` move the highlight (`aria-activedescendant`, focus stays in the input). `Tab` accepts the highlighted
  suggestion **as a chip**. `Enter` runs the search (or opens the highlighted saved search or collection).
  `Esc` closes the popover, then clears the text on a second press, then blurs on a third.
- Structured syntax is optional: `shot_size:close_up`, `-night` (exclude), `fps:>=50`, `duration:2s..10s`,
  `edit_type:selects`, `rights:allowed`, `in:transcript "quote"`, `similar:<shot-id>`. Typing `?` alone opens the
  syntax help popover.
- The search runs on `Enter` and **also** 400 ms after the last chip change (adding or removing a chip),
  but never per keystroke of free text.
- The URL updates (`?q=…&f=…`). Back and forward restore the state.

**States:** empty (placeholder *"Describe the shot you need, e.g. handheld street food close-ups at night"*,
`--fg-3`), typing, parsing, searching (a 2 px `--fg-2` progress line along the bottom edge after 400 ms,
static under reduced motion), error (border `--status-blocked`, message below with `circle-alert`).

**ARIA:** `role="combobox"`, `aria-expanded`, `aria-controls` (listbox), `aria-autocomplete="list"`, and the
label "Search shots" (visually hidden). Result counts are announced through the results header's
`role="status"`.

### 3.3 Facet chip / query chip (RAC `Tag` in `TagGroup`)

```text
┌────────────────────────────┐
│ SHOT SIZE  Close-up      × │   24 px tall, 4 px radius, 1 px --border-control
└────────────────────────────┘
  slate (mono 2xs, fg-3)  value (sans xs, fg-1, 500)  remove (14 px icon, 24×24 hit)
```

| State | Treatment |
|---|---|
| default | `--bg-raised`, border `--border-control` |
| hover | `--bg-hover`, border `--border-strong` |
| focus-visible | focus ring |
| **inferred** (from natural language) | value has a 1 px dotted underline in `--fg-3`. Tooltip: *From your words "close-ups"* |
| **excluded** | border dashed, slate reads `NOT SHOT SIZE`, value has a line-through |
| **disabled** (field not indexed yet) | `--fg-disabled`. Tooltip: *Shot size is still being analysed for 38 files* |

**Keyboard:** arrows move between chips, `Backspace`/`Delete` removes one (focus moves to the next chip, or
the input), `Enter` opens the chip editor (a popover with the facet's values), and `Alt+Enter` toggles
exclude. Pointer: click edits, `Alt+click` toggles exclude, and × removes. A trailing **Clear all** quiet
button appears when there are 2 or more chips.

**Copy:** slate labels use facet names in caps (`SHOT SIZE`, `MOVEMENT`, `TIME OF DAY`, `PLACE`, `EDIT STAGE`, `RIGHTS`,
`FPS`). Values are sentence case.

### 3.4 Filter rail

**Anatomy:**
- Header row: slate `FILTERS`, then the active count in `--key` (mono xs, e.g. `4`), then *Clear all*
  (quiet sm), then a collapse button (`panel-left`).
- Sections are RAC `Disclosure`s. Each facet maps 1:1 to a `search_shots` filter (ADR 011) and its values
  come from the controlled vocabularies (ADR 010; labels from `list_vocabularies`, never hard-coded). In
  this order:
  1. **Edit stage** (`edit_type`: Raw, Selects, Assembly, Rough cut, Fine cut, Locked cut, Finished,
     Programme recording, shown as an ordered list);
  2. **Rights** (intended use + verdict, see below);
  3. **Shot** (`shot_size`, `camera_angle`, `camera_movement`, `shot_role`, `lens_class`, `people_count`);
  4. **Content** (`setting`, named `people`, text in frame, has speech, language, `audio_class`);
  5. **Time and place** (`time_of_day`, `weather`, `season`, place, shoot date);
  6. **Look and feel** (dominant colour swatches, `mood`, `pace`);
  7. **Quality** (`quality_flag`; a *Hide major problems* switch is **on** by default, matching the API
     default of excluding severity ≥ major);
  8. **Technical** (orientation, minimum height, fps, duration, codec, bit depth, log/colour space, HDR,
     alpha, audio channels, safe crop available for 9:16 / 1:1 / 4:5);
  9. **Source** (`source_type`, camera, lens, ingest folder);
  10. **Collections**.
- Section header: slate label, then the active count (`--key`), then a chevron. 28 px tall, sticky within the
  rail (`--z-sticky`).
- Value row: a RAC `Checkbox` (16 px box, 24 px hit), label (`ui`), and count (mono xs `--fg-3`,
  right-aligned). Rows are 28 px.
  - Zero-count values stay visible in `--fg-disabled` with count `0`, and are not focusable unless *Show
    empty values* is on (an option in the section menu).
- Show the top 6 values, then *Show all 23*, which expands in place with a filter-within field (8 or more
  values).
- **Range facets** (fps, duration, resolution, shoot date) use a RAC `Slider` with two thumbs plus two
  `NumberField`s (or date fields). Typing is the non-drag alternative (2.5.7).
- **Colour facet:** a 6 × 2 grid of 24 px swatches (`role="checkbox"`, labelled "Warm orange", "Sodium yellow",
  "Teal", "Neon magenta", "Daylight blue", "Skin tones", …), each with a focus ring and a check glyph when on.
- **Rights section:** first an **Intended use** row (three compact pickers: *Usage*, *Channels*,
  *Territories*), which defaults to the workspace default set in *Rights → Policies* and is shown as a chip
  such as "Marketing · Organic social · GB". Verdicts on every card are computed **for this intended use**
  (`check_rights`, ADR 011). Below it, verdict checkboxes: Cleared (`allowed`), Restricted (`restricted`),
  Rights unknown (`unknown`), Blocked (`blocked`), each with a count. Then the switch *Hide blocked* is **on**
  by default (sends `require: "not_blocked"`). Turning it off shows blocked shots with a hatched overlay
  (§3.9). A permanent note sits under the section: *"Agents only ever see cleared shots."* (`info`,
  `--fg-3`).

**Behaviour:** desktop applies instantly (300 ms debounce across multiple changes). Tablet uses a drawer with
a sticky footer: **Show 412 shots** (primary) and *Reset*. Each facet's counts update with results
(`aria-live` off for counts). The results header announces the total.

**Keyboard:** `Tab` moves between sections and controls. Inside a checkbox list, arrows move and `Space`
toggles. `Alt+click` or `Shift+Space` on a value toggles **exclude** (row shows `not` and a line-through).

### 3.5 Results grid (RAC `GridList`, `layout="grid"`, inside `Virtualizer` with `GridLayout`)

- `selectionMode="multiple"`, `selectionBehavior="toggle"`, `disallowTypeAhead` when single-key shortcuts are
  on.
- **Override `Space`**: capture `keydown` on the grid wrapper so `Space` previews the focused shot instead of
  toggling selection. Selection toggles with `X` or `Ctrl/Cmd+Space` and extends with `Shift+Arrow`. The
  grid's `aria-description`: "Space previews, X selects, Enter opens."
- Header row (outside the grid):
  - count text: "412 shots in 38 files · 0.4 s" (`role="status"`);
  - **Shots | Files** segmented control (§3.13). *Files* switches to contact-sheet strips: one row per file,
    with the file name, edit stage and matching shots in sequence;
  - **View**: Grid / List / Log (`layout-grid`, `rows-3`, `list-video`);
  - **Size**: S / M / L;
  - **Sort**: Best match (default), Newest shoot, Oldest shoot, Duration, File name.
- **Match-strength divider:** a full-width row reading *Weaker matches below*, with hairlines either side
  (slate style), inserted where the score falls under the threshold. It is not focusable. A *Strictness*
  control in the header (Loose / Balanced / Strict) moves it.
- **Match-strength rail** (§3.22) on the right edge.
- **List view:** a RAC `Table` with columns thumbnail (64 × 36), timecode in/out, duration, description,
  file, edit stage, fps, resolution, rights.
- **Log view** (after Avid Script view): a 160 px thumbnail, then the description (prose) and transcript
  excerpt with query terms in `<mark>` (`--bg-selected` background, `--fg-1`), then signals.
- **Infinite loading:** 120 per page. The scroll height is **pre-allocated** from the total count. Unloaded
  cells render letterbox placeholders. There is no "Load more" button.
- **Context menu** on an item (right-click, `Shift+F10`, the Menu key, or the `ellipsis` button): Open, Open
  file, Preview, Find similar, Add to *active collection*, Add to…, Copy timecode, Copy shot reference,
  Edit tags, Rights…, Reveal in Finder/Explorer (desktop only).

### 3.6 Shot card (with scrub preview)

```text
            focus ring (2 px, 2 px off the card box)
            ┌ key ring (2 px gap + 2 px key, only when selected)
 ┌──────────────────────────────────┐
 │☑                       ⌕  ＋  ⋯ │ ← hover/selected only: select (24) · Find similar · Add · More (24 each, on scrim)
 │                                  │
 │        frame 16:9 (sprite)       │ ← letterboxed on --bg-letterbox; aspect label if not 16:9
 │                                  │
 │▮▮▮▮▮▮▮▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯│ ← scrub position bar, 2 px, --fg-on-scrim on --scrim, only while scrubbing
 └──────────────────────────────────┘
 00:14:03:12              6s · 50p ⛉   ← EDGE STRIP line 1: timecode (mono xs, leading zeros --fg-3) · duration · fps · rights glyph
 Close-up, hands at food stall, ste…   ← line 2: card-title (sans sm 500, 87.5% width), --fg-2
```

- **Dimensions:** frame is the card width × 9/16. The edge strip is 2 × 18 px plus 8 px top padding, so the
  card is frame + 44 px tall. There is no background behind the strip by default. Hover gives it `--bg-hover`
  with a 4 px radius on the bottom corners.
- **Frame overlays** (all on `--scrim` chips, 4 px radius):
  - top-left: selection checkbox (when hover, focus or selected);
  - top-right: actions (hover or focus only);
  - bottom-left: aspect label if not 16:9 (`9:16`, `2.39:1`, mono 2xs);
  - bottom-right: a *Human-edited* `pen-line` glyph if any signal was corrected.
- **Rights glyph** at the end of the strip, 16 px, `--status-*` colour:
  - Cleared `shield-check`, Restricted `shield-alert`, Expiring `calendar-clock`, Blocked or Expired
    `shield-x`, Unknown `circle-dashed`;
  - 24 × 24 hit area with a tooltip ("Cleared for all uses" / "Restricted: faces without release" /
    "Expires 12 Nov 2026");
  - the full text is also in the accessible name.
- **Blocked or expired** (when visible): the frame gets a 45° hatch (`repeating-linear-gradient` using
  `--scrim`) plus a centred scrim chip "Blocked". The preview still works for reviewers.
- **Edit stage** is not on the card (it is in the inspector header and the *Edit stage* facet). In *Files*
  grouping it is in the strip header.
- **Scrub** (pointer: fine, `data-scrub="on"`):
  1. On `pointerenter`, record x. Scrubbing starts **only after the pointer has moved ≥ 4 px inside the
     frame** (no accidental scrub).
  2. Frame index = `floor(x / width × 24)`. Swap `background-position` on the sprite `div` directly (a ref,
     not React state). The scrub bar shows the position.
  3. At `--delay-hover-intent` (150 ms) of hover, warm the preview MP4 (pooled `<video preload="auto">`).
  4. If the pointer **rests** for `--delay-preview-dwell` (400 ms) and `--preview-autoplay` is 1, play the
     preview muted from the scrubbed position, in place, over the sprite. Moving the pointer again pauses
     playback and returns to scrubbing.
  5. On `pointerleave`, restore the poster after 0 ms, stop and release the video to the pool.
- **Keyboard preview:** `Space` on the focused card plays the preview in place (play/stop toggle). `Alt+←/→`
  steps the sprite frame (a keyboard scrub). `J/K/L` shuttle the inline preview. `C` toggles captions.
- **Touch:** tap focuses and shows a 44 px play button centred on the frame. Tapping it plays.
- **Hover preview popover** (*Settings → Playback → Large hover preview*, off by default): a 480 px popover
  beside the card (`--z-preview`). It is hoverable, dismisses with `Esc`, and never covers the focused card
  (1.4.13).
- **Accessible name:** "{description}. {timecode in}, {duration}. {rights short}." For example: "Close-up,
  hands at food stall, steam. 00:14:03:12, 6 seconds. Cleared." The poster `<img alt="">` is decorative
  because the name already describes it.
- **States:** default, hover (actions shown, strip `--bg-hover`), focus-visible (ring, actions shown),
  selected (key ring and checked box), selected + focus, scrubbing, previewing (scrub bar hidden,
  `loader-circle` on the scrim after 400 ms if still buffering), blocked (hatch), missing media ("Source
  offline" scrim chip, `unplug` icon), processing ("Analysing…" chip with `loader-circle`, signals partial).

### 3.7 Timecode

- Format follows *Settings → Display → Timecode*: SMPTE `HH:MM:SS:FF` (default, `;` before frames for
  drop-frame), frames `#21342`, or seconds `14:03.48`.
- The leading `00:` groups render in `--fg-3`, so the significant digits read first. Hours always show
  (2 digits).
- Sizes: `xs` (edge strip), `sm` (tables, inspector), `xl` (player readout, weight 500).
- **Click to copy** (when it is a standalone element, not inside a card). Toast: "Copied 00:14:03:12".
- **Accessible name:** `aria-label="14 minutes, 3 seconds, 12 frames"`. Hours are omitted when zero. The visible
  text is `aria-hidden`.
- **Ranges:** `00:14:03:12 → 00:14:09:12` with an `→` in `--fg-3`, plus the duration in parentheses where
  space allows.

### 3.8 Confidence meter

```text
▮▮▮▮▯  91
```

- Five 6 × 8 px segments (2 px radius, 2 px gap), then the numeric value (mono xs, `--fg-2`, no `%`).
  - Filled segments are `--fg-2` and empty ones `--viz-1`. Segments filled = `round(confidence × 5)`.
- **Bands:** ≥ 0.85 *high*, 0.60–0.85 *medium*, < 0.60 *low*. Low-band segments get a 1 px dashed
  `--border-control` outline and the word "low" after the number (`--fg-3`).
- The meter is **never** red/green. Confidence is not good or bad, it is certainty.
- `role="meter"`, `aria-valuemin=0`, `aria-valuemax=100`, `aria-valuenow=91`,
  `aria-valuetext="91 percent, high confidence"`.
- Human-confirmed or human-corrected values show **no meter** (§3.10).

### 3.9 Rights badge

| Status | Icon | Colour | Short text | Long text example |
|---|---|---|---|---|
| Cleared | `shield-check` | `--status-cleared` | Cleared | Cleared for all uses · location release on file |
| Restricted | `shield-alert` | `--status-caution` | Restricted | Restricted: editorial use only / faces without release / UK only |
| Expiring (≤ 30 days) | `calendar-clock` | `--status-caution` | Expires 12 Nov | Licence expires 12 Nov 2026 (39 days) |
| Expired | `shield-x` | `--status-blocked` | Expired | Licence expired 1 Oct 2026 |
| Blocked | `shield-x` | `--status-blocked` | Blocked | Blocked by Priya: talent withdrew consent |
| Unknown | `circle-dashed` | `--fg-3` | Rights unknown | No rights information yet |

**API mapping** (`check_rights`, ADR 011):
- `allowed` → Cleared;
- `restricted` → Restricted (show the first reason and any requirement, such as a credit line);
- `blocked` → Blocked, or Expired when the reason code is expiry;
- `unknown` → Rights unknown, **never** treated as cleared.

*Expiring* is derived on the client when the verdict is `allowed` or `restricted` and `expires_at` is
≤ 30 days away.

Sizes:
- **glyph** (card: icon only, accessible name plus tooltip);
- **compact** (icon + short text in sans xs 500, on a `--status-*-bg` chip, 20 px tall, 4 px radius);
- **full** (inspector block: icon + long text + metadata lines in `--fg-2` + *Change* quiet button `R`).

Agents: a line in the full block, "Agents: visible" or "Agents: hidden (not cleared)".

### 3.10 Signal row

Signals are the facts Metachlorian holds about a shot. They are shown in a RAC `Table` (compact, no header
row in the inspector; a header in Corrections).

```text
SHOT SIZE    Close-up                 Vision model     ▮▮▮▮▯ 91        ✓  ✗  ✎
TIME OF DAY  Night                    Vision model     ▮▮▮▮▯ 88        ✓  ✗  ✎
CROWD        Busy  [✎ Sam · 2 Oct]    Human            —               ↺
PLACE        Bangkok, Chinatown       GPS + geocoder   ▮▮▮▮▮ 99        ✓  ✗  ✎
OBJECTS      Wok, steam, ~~cat~~      Vision model     …               (cat removed by Sam · Undo)
```

- **Columns:** slate label (96 px) · value (`ui`, wraps to 2 lines) · source (`--fg-3` xs: *Vision model*,
  *Motion analysis*, *Audio*, *Transcript*, *Camera metadata*, *GPS + geocoder*, *Human*) · confidence (§3.8)
  · actions (24 px quiet icon buttons: `check` *Confirm*, `x` *Remove*, `pen-line` *Edit*. Visible on row
  hover or focus-within, always visible on coarse pointers).

| State | Visual | Meaning |
|---|---|---|
| suggested | value `--fg-1`, meter shown | Model output, not reviewed |
| **confirmed** | small `check` glyph + "Confirmed by Sam" (`--fg-3` xs) replaces the meter | A human agreed. Search treats it as certain. |
| **corrected** | **human marker chip**: `--bg-inverse` fill, `--fg-inverse` text, `pen-line` 12 px + "Sam · 2 Oct", 20 px tall, 2 px radius. The model's original value appears on hover or focus: "Model said: Calm (0.62)" | A human changed the value. It **outranks the model permanently** and survives re-analysis. |
| **removed** | value with line-through in `--fg-3` + "Removed by Sam · Undo" | Excluded from search |
| **disputed** | corrected chip + an `info` line: "Model now suggests: Wide (0.72). Keep yours / Use model" | Re-analysis disagrees. The human value still wins until someone chooses. |
| pending | value + `loader-circle` 14 + "Re-analysing" | The value stays visible. No flicker. |

The human marker is distinguished by **shape and fill** (an inverse solid chip), not by hue. **"It sticks"**
copy appears once, in the toast after a correction: "Saved. This tag will stay as you set it, even if the
shot is re-analysed." with *Undo*.

**Keyboard** (in the signal table): arrows move between rows. `Enter` confirms. `Delete` removes. `E` edits
(an inline RAC `ComboBox` with the facet vocabulary and "Create 'busy'"). `Esc` cancels. `⌘/Ctrl+Enter`
applies the edit to all selected shots (with a confirm count: "Apply to 12 shots?").

### 3.11 Filmstrip / timeline (hand-rolled on `useMove` and `useSlider`)

```text
MATCHES  ▬▬▬▬     ▬▬            ▬▬▬▬▬▬               ▬▬▬                  ▬▬        8 px lane, --fg-2; current match --key
SHOTS   ┃▓▓▓┃▓▓▓▓▓┃▓▓┃▓▓▓▓▓▓▓▓┃▓▓▓┃▓▓▓▓▓▓▓▓▓▓┃▓▓┃▓▓▓▓▓▓▓┃▓▓▓▓┃▓▓▓▓▓▓▓┃          48 px thumbnail lane, 1 px --bg-canvas boundaries
RIGHTS                     ╱╱╱╱╱╱╱╱                    ╱╱╱╱                  6 px hatched lane, caution/blocked
         00:00     05:00     10:00     15:00     20:00     25:00     30:00   ruler, mono 2xs --fg-3
                       ▼ playhead: 2 px --key line + timecode flag (mono xs on --key, --fg-on-key)
                 [═════════]  in/out brackets in --fg-1, range tint --bg-selected
```

- **Height:** `--filmstrip-height` (96) = matches 8 + gap 4 + shots 48 + gap 4 + rights 6 + ruler 16 + padding.
- **Thumbnails** come from the asset sprite (one frame per 2 s at 96 × 54), drawn as background tiles. They
  are virtualised horizontally with TanStack Virtual when zoomed.
- **Zoom:** `+`/`-`, `Ctrl/Cmd+scroll`, or pinch. `Shift+Z` fits. Plain scroll **never** zooms; it scrolls
  horizontally when zoomed in. A zoom slider and buttons sit at the right end.
- **Pointer:** click moves the playhead. Drag on the shots lane scrubs. `Shift+click` sets a range from the
  playhead. Drag edges of the in/out range to trim, with `I`/`O` as the non-drag alternative (2.5.7).
- **ARIA:**
  - the container is `role="group"` with `aria-label="Timeline, Market_Night_A012.mov"`;
  - the playhead is `role="slider"` with `aria-valuemin=0`, `aria-valuemax={frames}`,
    `aria-valuetext="00:14:05:02, shot 14 of 63, close-up, cleared"`;
  - matches and rights lanes are `aria-hidden`. Their information is in the valuetext and in the shot
    table below;
  - entering a new shot announces it via a polite live region at most once per 500 ms.

### 3.12 Player and transport

- The player well is `--bg-well` and the video uses `object-fit: contain`. **Player chrome sets
  `color-scheme: dark`**, so controls are dark in both themes.
- **Transport row** (32 px buttons):
  - left: timecode readout (xl mono, click to type a timecode);
  - centre: `skip-back` (previous shot), J, play/pause, L, `skip-forward` (next shot);
  - right: I, O, captions, speed (`1×`), volume, full screen.
- The mini timeline above the transport is a slider with the in/out range in `--bg-selected` and the
  playhead in `--key`.
- **Start budget:** the poster is shown immediately. The proxy is prefetched on hover intent (Shot open
  link) and on focus rest (250 ms) in the grid. `preload="auto"` once the inspector shows a shot. Playback
  begins at the shot's in-point (`#t=`).
- **Captions:** a transcript-derived WebVTT track, off by default unless the OS caption preference is on.
  `C` toggles. Captions sit on `--scrim`, sans md, bottom-centred, never over the timecode flag.
- **Audio:** previews are always muted. The player starts unmuted at the last-used volume. `M` mutes.

### 3.13 Segmented control (RAC `ToggleButtonGroup`, single selection, `disallowEmptySelection`)

- 28 px tall, a 1 px `--border-control` outer border, 4 px radius, 1 px `--border-subtle` dividers.
- Segment: icon (16) and/or label (`ui`). Icon-only segments need `aria-label` plus a tooltip.
- **Selected:** `--bg-pressed`, `--fg-1`, weight 600, **plus a 2 px bottom bar in `--fg-1`**. The bar is the
  ≥ 3:1 state cue. Unselected segments are `--fg-2`.
- **Keyboard:** arrow keys move and select (radio-like). `Tab` leaves the group.
- **Uses:** Shots | Files, Grid | List | Log, S | M | L, Loose | Balanced | Strict, Theme.

### 3.14 Selection bar

- Appears across the full window width, below the three panes, when ≥ 1 shot is selected (no motion under reduced motion, otherwise a
  `--dur-3` slide). It is 48 px, `--bg-panel` with a `--border-default` top edge.
- Left: "**3** selected" (`ui-strong`, count in tabular numerals) + *Select all 412* (quiet) + *Clear* (`Esc`).
- Right:
  - *Add to Selects* `B` (secondary; label uses the active collection's name);
  - *Add to…* `A`;
  - *Find similar* `S`;
  - *Rights…* `R`;
  - *Export* `⌘E` (menu: OTIO, FCPXML, CMX 3600 EDL, FCP7 XML, CSV);
  - **Send to Cutawan** `⌘⇧E` (**primary**).
- Shortcut hints are in mono 2xs `--fg-3` inside each button, hidden below 1280 px.
- *Send to Cutawan* and *Export* always run the rights check for the dialog's intended use first
  (`build_package` repeats it, ADR 011/012). Blocked and unknown shots are **dropped** and listed. Restricted
  shots need an explicit choice: "2 of 14 shots are restricted (credit required). Include them?" There is no
  silent inclusion.

### 3.15 Toast (RAC `Toast` / `ToastRegion`)

- Bottom centre of `main`, 16 px above the selection bar. 360–480 px wide, `--bg-overlay`,
  `--shadow-popover`, 6 px radius, 12/16 padding.
- Anatomy: status icon (16) + message (`ui`, up to 2 lines) + optional action (quiet button, e.g. *Undo*) +
  close (`x`, 24).
- **Timing:** `--toast-duration` (6 s) for success and info, paused while hovered or focused. **Errors never
  auto-dismiss.** At most 3 stack (newest at the bottom).
- The region is an `F6` landmark ("Notifications"). `role="status"` for info/success and `role="alert"` for
  errors.
- **Don't** toast what is already visible (for example, a chip added). Do toast: added to collection, sent to
  Cutawan, export ready, correction saved, copy actions.

### 3.16 Empty, error and loading states

All are rendered in `main` at the place the content would be (never as a dialog). Layout: optional 20 px icon
(`--fg-3`), headline (`--text-lg`, 600), one line of `prose`, and up to 2 actions. Left-aligned at 64ch, with
the top at 25% of the region.

| State | Headline | Body / actions |
|---|---|---|
| First run, empty library | Add your first footage | "Point Metachlorian at a folder. Files stay where they are, and we only read them." [Add a folder] [Read how indexing works] |
| No results | No shots match "handheld street food close-ups at night" | "Removing **night** would show 1,204 shots. Removing **handheld** would show 318." Each is a button that removes the chip. [Clear all filters] |
| Filters exclude everything | Your filters hide all 412 matches | List the 2 most restrictive filters as buttons. |
| Still indexing | Results will improve as analysis finishes | "312 of 1,040 files analysed. Shots from the rest appear automatically." Inline, above results, not instead of them. |
| Search failed | Search didn't work | "The search service didn't respond in 10 seconds." [Try again] plus a details disclosure with a copyable error ID. |
| Offline (web) | You're offline | "Results you've already seen are still here. New searches need a connection." |
| Empty collection | Nothing in Selects yet | "Select shots and press **B** to add them here." |
| No permission | You can't see this collection | "Ask an admin to give you access." |

**Loading:** nothing for the first 400 ms. Then a 2 px progress line under the search bar (indeterminate
sweep, or a static 30% bar under reduced motion) plus the count text "Searching…". Grid placeholders are
letterbox wells at final size (no shimmer). Panels that are loading keep their previous content with
`aria-busy="true"`.

### 3.17 Dialog (RAC `Modal` + `Dialog`)

- Widths: S 400, M 560, L 800 (tablet: min(width, 100% − 32 px)). `--bg-overlay`, `--shadow-dialog`, 8 px
  radius, 24 px padding. Backdrop is `rgb(0 0 0 / 0.5)` (dark) / `0.32` (light).
- Title (`title` role, `--text-xl`), body (`prose`), and a footer with buttons right-aligned. The **primary is
  rightmost**. Cancel is secondary. Destructive confirmations use a filled danger button with a specific
  verb ("Remove 3 shots").
- Focus goes to the first field, or to the **least destructive** button in confirms. It returns to the
  trigger on close. `Esc` closes unless a form is dirty, in which case it asks "Discard changes?".
- **Send to Cutawan dialog** (L). Fields map to `build_package` and the package manifest
  (`docs/integration/cutawan-contract.md`):
  - **Package name** (default "Selects · 4 Oct 2026") and a **brief/note** (`prose` textarea, 64ch, reading
    mode).
  - **What Cutawan should make** (`cutawan.mode`), as a radio group with one-line explanations:
    - *A-roll with B-roll inserts* (default for social rough cuts);
    - *Stringout* (one conformed video);
    - *B-roll library* (no project, feeds Cutawan's B-roll picker).
  - **Aspect**: 9:16 / 1:1 / 4:5 / 16:9 / Original. Shots without a safe crop for the aspect show a
    `triangle-alert` in the list.
  - **Intended use** (usage, channels, territories), prefilled from the search's intended use.
  - **Media** (`media_policy`): Stringout / Proxies / Trimmed originals / None. **Handles**: NumberField, 1 s
    default.
  - **Timelines**: checkboxes for OTIO, FCPXML 1.10, CMX 3600 EDL (all on).
  - **Shot list**: order, role (A-roll / B-roll) and in/out. Reorder with `⌥↑/⌥↓` or drag.
  - **Rights summary** (live `check_rights`): "12 cleared · 2 restricted · 0 blocked · 0 unknown", plus
    credits required, earliest expiry, and the restricted decision described in §3.14.
  - Primary: **Send 12 shots** (the count updates with the rights decision). On desktop it launches
    `cutawan --import-package <dir>` through the capabilities bridge. On web it offers **Download package
    (.zip)** instead.
- **Export dialog** (M), following ADR 012:
  - format: OTIO, FCPXML 1.10 (1.9 for Resolve 17; 1.11+ selectable), CMX 3600 EDL (V1 only), FCP7 XML
    (opt-in, for Premiere < 26), CSV shot list;
  - frame rate, handles, reel-name source, media (none / proxies / trimmed originals);
  - destination: a folder on desktop, a download on web.

### 3.18 Menu (RAC `Menu`, `MenuTrigger`, `SubmenuTrigger`, `Popover`)

- `--bg-overlay`, `--shadow-popover`, 6 px radius, 4 px padding. Min 200 px, max 320 px.
- Item: 28 px (32 comfortable, 44 coarse), 8 px horizontal padding, icon 16 (`--fg-2`), label (`ui`), and a
  right-aligned shortcut (mono 2xs `--fg-3`). Hover and focus use `--bg-hover`. Destructive items use
  `--status-blocked` text and icon.
- Sections are separated by a 1 px `--border-subtle` with an optional slate header. Submenus use
  `chevron-right`.
- **Keyboard:** arrows, `Home`/`End`, typeahead, `Enter`/`Space`, `→` opens a submenu, `←`/`Esc` closes.
  Checkable items use `menuitemcheckbox` / `menuitemradio`.

### 3.19 Table (admin) (RAC `Table`, `Virtualizer` with `TableLayout` past 200 rows)

- Header: slate style (mono 2xs caps `--fg-3`) on `--bg-raised`, sticky, 32 px. Sortable columns show an
  arrow and `aria-sort`.
- Rows are `--table-row-height` with 1 px `--border-subtle` dividers and no zebra striping. Numbers are
  right-aligned in tabular figures. Dates use "4 Oct 2026, 14:05".
- Selection: a leading checkbox column (24 px hit). Selected rows use `--bg-selected` and a 2 px `--key`
  leading bar.
- Row actions: a trailing `ellipsis` menu (always visible) plus inline quiet buttons on hover or
  focus-within.
- Empty: a single row spanning all columns, with the empty-state copy.
- **Keyboard (APG grid):** arrows move between cells, `Enter` opens the row, `Space` toggles row selection,
  and `⌘/Ctrl+A` selects all.

### 3.20 Egress indicator ("content leaves this machine")

- In the **top bar** at all times:
  - *Local* (`hard-drive` 16, `--fg-2` text "Local") when every active model adapter runs on this machine
    or server;
  - **Leaves this machine** (`cloud` 16 + text, `--status-caution` on `--status-caution-bg` chip, 24 px)
    when any active adapter sends frames, audio or text elsewhere.
- Clicking opens a popover. It lists each active adapter with what leaves ("Frames (1 per second, 512 px)",
  "Audio", "Transcript text"), where it goes (domain, region) and when (ingest only / every search). It links
  to *Settings → Model adapters*.
- In **Settings → Model adapters** every adapter row carries the same chip. Enabling a remote adapter opens a
  confirm dialog:
  > "**Frames from your footage will be sent to api.example.com.** This happens during analysis of every new
  > file. Footage files themselves are not uploaded." [Turn on and send frames] [Cancel]
- On **Ingest**, files analysed with a remote adapter show the chip in their row.

### 3.21 Tooltip (RAC `Tooltip`)

- `--bg-inverse` / `--fg-inverse`, sans xs, 4 px radius, 6/8 padding, max 280 px, `--shadow-popover`.
  Shortcut keys appear in mono after the label.
- Opens after `--delay-tooltip` on hover, **immediately on keyboard focus**, and closes with `Esc` (1.4.13).
  It never contains interactive content.

### 3.22 Match-strength rail

- A 12 px column at the right edge of the results scroller. It shows a vertical sparkline of match scores
  down the result list (`--viz-2`→`--viz-4`), a tick at the *Weaker matches below* divider, and a thumb
  showing the viewport (`--border-strong` outline).
- Dragging or clicking jumps. It is a `role="scrollbar"` with `aria-controls` pointing at the grid and
  `aria-valuenow` as a percentage. `PageUp`/`PageDown` on the grid serve as the keyboard equivalent.
- When sorted by date, it shows month ticks instead (the Google Photos pattern).

### 3.23 Processing status (ingest row)

- A table row: file name, size, a stage list rendered as **steps**:
  - `Probe · Proxies · Shots · Vision · Audio · Index`;
  - each step is a 14 px glyph: done `check` in `--fg-2`, active `loader-circle` (static under reduced
    motion) in `--key`, waiting `circle-dashed` `--fg-3`, failed `circle-x` `--status-blocked`.
- Then the overall percentage (mono) and ETA ("about 4 min"), plus the egress chip if remote.
- Failed rows show the reason in plain words and *Retry*. "Proxies failed: the file uses a codec ffmpeg
  can't read (Blackmagic RAW). Install the BRAW plug-in or convert the file."
- Live updates are throttled to 1 per second per row. A summary is announced in a polite live region at
  most every 10 s: "Ingest: 12 of 40 files ready".

### 3.24 Command menu (`⌘/Ctrl+K`)

- A dialog (M width, top-aligned at 15vh) containing an input with `aria-activedescendant` over a grouped
  listbox: *Actions* (with shortcuts), *Go to*, *Saved searches*, *Collections*, *Recent shots*.
- Typing filters with fuzzy matching. `Enter` runs the item, `Esc` closes, and `⌘/Ctrl+K` again closes.
- Every action in the app is reachable here. This is the escape hatch for remapped or disabled single-key
  shortcuts.

---

## 4. Motion rules

1. **Motion explains continuity, never decorates.** The allowed movements are:
   - popovers and menus fading and scaling from 0.98 (`--dur-3`, `--ease-enter`);
   - dialogs fading and translating 8 px up (`--dur-4`);
   - panels collapsing (`--dur-3`);
   - the selection bar sliding up 8 px (`--dur-3`);
   - chips added or removed (`--dur-2` width and opacity);
   - the **card → inspector flight** (`--dur-3`), where the poster's rect animates to the player rect with
     the View Transitions API (`view-transition-name: shot-{id}`).
2. **Exits are faster than entrances** (`--dur-2`, `--ease-exit`).
3. **No bounce, no overshoot, no parallax, no auto-advancing carousels, no looping UI animation**, except the
   progress line and the `loader-circle` spin, and both become static under reduced motion.
4. **Scrolling is never hijacked.** `scroll-behavior: smooth` is applied only to programmatic jumps (the
   match rail, "Back to top"), and never under reduced motion.
5. **Video:** no autoplay. Dwell previews play only under the pointer, loop at most 3 times, then stop on
   the last frame.
6. **Reduced motion** (`prefers-reduced-motion: reduce` or `data-motion="reduced"`):
   - every duration becomes 0 ms;
   - `--preview-autoplay` becomes 0 (dwell never plays; `Space` still does);
   - the View Transition is skipped;
   - progress indicators become static;
   - **pointer scrubbing stays enabled**, because it is direct manipulation of a still image.
7. Never animate `width`/`height` of grid cells or anything inside the virtualised grid. Animate only
   `opacity` and `transform`.

---

## 5. Keyboard map

**Conventions:** `⌘` on macOS is `Ctrl` on Windows/Linux, and `⌥` is `Alt`.

**Single-key shortcuts (WCAG 2.1.4):**
- They are active **only while their region has focus** (results grid, player, timeline, signal table) and
  never while a text field has focus.
- *Settings → Keyboard* has a master switch, **Single-key shortcuts: On/Off**, and a remap table (record a new
  key, conflicts flagged).
- When they are off, grid typeahead switches on, and every action stays reachable via `⌘K`, menus and
  buttons.
- `?` (or `⌘/`) opens the shortcut sheet. It is a dialog with a two-column table per surface, searchable.

### 5.1 Global (any focus)

| Keys | Action |
|---|---|
| `⌘K` | Command menu |
| `⌘F`, or `/` (single key) | Focus search |
| `⌘1` … `⌘5` | Go to Search · Library · Collections · Ingest · Rights |
| `⌘,` | Settings |
| `⌘\` | Toggle filter rail |
| `⌘I` | Toggle inspector |
| `F6` / `⇧F6` | Next / previous region |
| `⌘Z` / `⇧⌘Z` | Undo / redo (selection, collection edits, corrections, rights changes) |
| `⌘=` / `⌘-` / `⌘0` | Thumbnail size up / down / reset |
| `⌘E` | Export selection |
| `⇧⌘E` | Send selection to Cutawan |
| `?`, `⌘/` | Keyboard shortcuts |
| `Esc` | Close the topmost layer. In the grid with no layer open: stop the preview, then clear the selection. |

### 5.2 Search bar and suggestions

| Keys | Action |
|---|---|
| `↓` / `↑` | Move through suggestions |
| `Tab` | Accept the suggestion as a chip |
| `Enter` | Run the search, or open a saved search or collection |
| `⌘Enter` | Run the search and focus the first result |
| `Backspace` at start of input | Focus the last chip |
| `Esc` | Close suggestions → clear text → leave the field |

### 5.3 Results grid (region-scoped single keys)

| Keys | Action |
|---|---|
| `←` `→` `↑` `↓` | Move focus |
| `Home` / `End`, `⌘Home` / `⌘End`, `PageUp` / `PageDown` | Row start/end, first/last result, page |
| `Space` | Play or stop the inline preview of the focused shot |
| `⌥←` / `⌥→` | Step the scrub frame (keyboard scrub) |
| `J` / `K` / `L` | Shuttle the inline preview (reverse, stop, forward; repeat to go faster) |
| `Enter` | Open Shot detail |
| `X`, `⌘Space` | Toggle selection of the focused shot |
| `⇧X` | Toggle selection and move to the next shot (Lightroom-style auto-advance) |
| `⇧←→↑↓` | Extend selection |
| `⌘A` / `⇧⌘A` | Select all results / clear selection |
| `B` | Add to the active collection |
| `⇧B` | Add to the active collection and move to the next |
| `A` | Add to… (collection picker) |
| `S` | Find similar (focused, or the selection as a group) |
| `E` | Edit tags (opens Corrections for the focused shot in the inspector) |
| `R` | Rights for the selection |
| `C` | Captions on inline previews |
| `G` | Toggle Shots / Files grouping |
| `V` | Cycle view: Grid → List → Log |
| `⌘C` | Copy shot reference(s): `path · TC in → TC out` |
| `Delete` (in a collection) | Remove from the collection (toast with *Undo*) |
| `⌥↑` / `⌥↓` (in a collection) | Move the shot earlier or later (the non-drag reorder) |
| `Shift+F10`, Menu key | Context menu |

### 5.4 Player (Shot detail and Asset view; region-scoped)

| Keys | Action |
|---|---|
| `Space` | Play / pause |
| `⇧Space` | Play from in to out |
| `J` / `K` / `L` | Reverse / stop / forward. Repeat for 2×, 4× or 8×. Hold `K` + tap `J`/`L` to step one frame. |
| `←` / `→` | Back / forward one frame |
| `⇧←` / `⇧→` | Back / forward one second |
| `↑` / `↓` | Previous / next shot boundary |
| `Home` / `End` | Start / end of file |
| `I` / `O` | Set in / out |
| `⇧I` / `⇧O` | Go to in / out |
| `⌥I` / `⌥O` / `⌥X` | Clear in / clear out / clear both |
| `T`, or type digits | Go to timecode (opens the readout field) |
| `C` / `M` / `F` | Captions / mute / full screen |
| `S` `B` `A` `E` `R` | As in the grid, for the current shot |
| `[` / `]` | Previous / next result (Shot detail opened from results) |

### 5.5 Asset view timeline

The player keys apply, plus:

| Keys | Action |
|---|---|
| `+` / `-`, `⇧Z` | Zoom in / out, fit |
| `X` | Select the shot under the playhead (as in FCP) |
| `⇧↑` / `⇧↓` | Extend the shot selection to the previous / next shot |
| `Enter` | Open Shot detail for the shot under the playhead |
| `Tab` | Leave the timeline for the shot table |

### 5.6 Corrections (signal table)

| Keys | Action |
|---|---|
| `↑` / `↓` | Move between signals |
| `Enter` | Confirm the value |
| `E` | Edit the value (inline combobox) |
| `Delete` | Remove the value |
| `⌘Enter` | Apply the edit to all selected shots |
| `Esc` | Cancel the edit |
| `⌘Z` | Undo |

### 5.7 Tables, menus and dialogs

These follow the RAC defaults, which are the APG patterns: grid navigation and `Space` to select in tables;
arrows, typeahead and `Enter` in menus; `Tab` cycling and `Esc` to close in dialogs.

---

## 6. Performance budget and preview pipeline

| Interaction | Budget (p95) | How |
|---|---|---|
| Keystroke → chip feedback | ≤ 50 ms | Local tokenizer, no network |
| Search submit → first row painted | ≤ 600 ms (server ≤ 250, network ≤ 100, render ≤ 100, first-row image decode ≤ 150) | 120-item pages. Posters ≤ 25 KB WebP. `fetchpriority="high"` on the first row only. |
| Scroll | 60 fps, no long task > 50 ms | Virtualizer. ≤ 12 DOM nodes per card. `contain: layout paint style` on cards. No shadows or filters in the scroller. Images have fixed size and `decoding="async"`. |
| Hover scrub frame swap | ≤ 1 frame | Sprite `background-position` via ref. The sprite loads with the poster for visible rows plus 1 row of overscan. |
| `Space` / dwell → first preview frame | **≤ 300 ms** | A pool of 4 `<video muted playsinline>`, warmed at 150 ms of hover intent or 250 ms of focus rest. Preview MP4 is 480p, faststart, 0.5 s GOP. Local `mc-media://` protocol with Range in Electron. |
| Open shot → player first frame at in-point | ≤ 300 ms (local) / ≤ 500 ms (LAN web) | The proxy is prefetched (`preload="metadata"`) for the focused shot. 720p, faststart, 1 s GOP. Poster shown instantly. |
| Correction saved → visible everywhere | ≤ 150 ms optimistic, server confirm ≤ 1 s | TanStack Query optimistic update plus invalidation of the affected search pages |
| Memory after 10,000 results scrolled | ≤ 600 MB renderer | LRU of 600 decoded sprites. Release `src` on pooled videos when idle. |

These numbers are the acceptance gates in ADR 013 (`bench/`).

---

## 7. Iconography

- **Lucide** (`lucide-react`, ISC licence, the same set as Cutawan). Stroke width is **1.75** at 16 and 20 px,
  and 2 at 14 px. `currentColor` only. Always `aria-hidden="true"`; the accessible name comes from text or
  `aria-label`.
- Sizes: 14 (inside chips and badges), 16 (default, rows, buttons), 20 (top bar, empty states). Never larger
  in UI chrome.
- No filled icon variants, no coloured icon tiles, no emoji.

**Canonical mapping** (names verified against lucide-static 1.51.0):

| Concept | Icon | Concept | Icon |
|---|---|---|---|
| Search | `search` | Find similar | `scan-search` |
| Filters | `sliders-horizontal` | Exclude filter | `list-filter` |
| Shot | `film` | Asset / file | `file-video-camera` |
| Raw | `aperture` | Selects | `scissors` |
| Finished edit | `clapperboard` | Collection | `layers` |
| Smart collection / saved search | `list-filter` | Library overview | `library` |
| Rights cleared | `shield-check` | Restricted | `shield-alert` |
| Expiring | `calendar-clock` | Blocked / expired | `shield-x` |
| Rights unknown | `circle-dashed` | Human correction | `pen-line` |
| Confirm | `check` | Remove / close | `x` |
| Undo | `undo-2` | History | `history` |
| Ingest | `cloud-upload` (remote), `hard-drive` (local folder) | Processing | `loader-circle` |
| Error | `circle-alert` | Warning | `triangle-alert` |
| Info | `info` | Leaves this machine | `cloud` |
| Local only | `hard-drive` | Model adapter | `cpu` |
| API token | `key-round` | Agent | `bot` |
| Users | `users` | Roles | `user-cog` |
| Settings | `settings` | Keyboard | `keyboard` |
| Send to Cutawan | `send` | Package | `package` |
| Export | `download` | Copy | `copy` |
| Grid view | `layout-grid` | List view | `rows-3` |
| Log view | `list-video` | Filter rail / inspector | `panel-left` / `panel-right` |
| Play / pause | `play` / `pause` | Prev / next shot | `skip-back` / `skip-forward` |
| Volume / muted | `volume-2` / `volume-x` | Captions | `captions` |
| Place | `map-pin` | Tag | `tag` |
| More | `ellipsis` | Source offline | `unplug` |

---

## 8. Copy and voice

**Voice:** a calm, exact colleague, the assistant editor who knows where everything is. Write in **British
English**, **sentence case**, plain words, active voice, and no exclamation marks.

| Do | Don't |
|---|---|
| Add to Selects | Add To Selects |
| 412 shots in 38 files | 412 Results Found! |
| Couldn't read this file. It uses a codec ffmpeg doesn't support. | Oops! Something went wrong. |
| Leaves this machine | Cloud-powered AI ✨ |
| Analysing · Colour · Licence (noun) · Organise · Catalogue | Analyzing · Color · License (noun) · Organize · Catalog |
| Removing **night** would show 1,204 shots | Try a different search |
| Sam corrected this | User edited |
| Blocked: talent withdrew consent | Error 403 |

**Glossary** (use these words, consistently):

| Term | Meaning |
|---|---|
| **Shot** | A continuous range in a file, with in/out |
| **File** | The source media. Use "asset" only in the API. |
| **Edit stage** | Raw, Selects, Assembly, Rough cut, Fine cut, Locked cut, Finished, Programme recording (`edit_type`) |
| **Shot role** | A-roll, B-roll, Establishing, Cutaway and so on (`shot_role`) |
| **Signal** | A fact about a shot, with a source and confidence |
| **Suggested / Confirmed / Corrected / Removed** | Signal states |
| **Collection** | A static set of shots, for example *Selects* |
| **Saved search** | A dynamic collection driven by a query |
| **Cleared / Restricted / Expires / Expired / Blocked / Rights unknown** | Rights states. API verdicts `allowed` / `restricted` / `blocked` / `unknown`, plus `expires_at` (§3.9) |
| **Send to Cutawan** | Hand off a package to Cutawan |
| **Export** | Write an EDL, FCPXML, OTIO or CSV file |
| **Agent** | A program using an API token |
| **Model adapter** | A configured analysis model |
| **Leaves this machine** | Any adapter that sends content off-device |

**Formats**
- Numbers: `1,204`. Durations: `6s`, `1m 12s`, `41:12` (file length). Timecode: §3.7.
- Dates: `4 Oct 2026`. With time: `4 Oct 2026, 14:05` (24-hour). Relative only under 7 days ("2 days ago",
  with the absolute date in a tooltip).
- File sizes: `1.2 GB` (decimal units, with a space).

**Message patterns**
- **Errors:** what happened, then why if known, then what to do. Give one action button, named with a verb.
- **Confirmations:** a question with the count and object ("Remove 3 shots from Selects?") and buttons that
  repeat the verb ("Remove 3 shots" / "Cancel").
- **AI language:** say "Metachlorian found", "suggested" or "the vision model". Never "magic", "smart" or
  "AI-powered".

---

## 9. Surface blueprints

Each surface uses the shell (§2.1) unless noted. The wireframes for Search, Shot detail and Asset view are in
`directions.md` §1 (A1–A3) and are normative.

1. **Search** (`/search?q=…`): the top bar search, filter rail, results grid, inspector and selection bar.
   The inspector follows grid focus after 150 ms (it shows the focused shot) and *pins* when a shot is
   opened with `Enter` (Shot detail page).
2. **Shot detail** (`/shot/:id`). The left column holds:
   - the player and transport;
   - *Why it matched* (prose, one line per query term: `"term" → field: value (confidence, source)`);
   - *Similar shots* (a 1-row grid of 8, `S` for all).

   The right column (384) holds:
   - shot description (prose);
   - in/out and technical line (mono);
   - **Signals** (§3.10, `E` to edit);
   - **Rights** (§3.9 full, `R`);
   - **In collections** (chips);
   - **File** (edit stage, path, link to the Asset view).

   `[`/`]` move to the previous or next result.
3. **Asset view** (`/file/:id`):
   - header with file name, edit stage (editable menu, `edit_type`), shot count, length and
     rights summary;
   - player beside the file metadata;
   - **filmstrip** (§3.11) full width;
   - shot table (RAC `Table`: #, in, out, duration, shot size, movement, time of day, tags, rights). The row under the
     playhead is highlighted (`--bg-pressed`).
4. **Collections** (`/collections`, `/collections/:id`):
   - a left list of collections (Tree, with the static vs saved-search icon) replaces the filter rail;
   - the main area shows the collection's shots in the grid (List view by default for collections, since
     order matters);
   - reorder by drag **or** `⌥↑/⌥↓` / *Move up* / *Move down* in the menu (2.5.7);
   - the header has the collection name (editable), note (prose), shot count, total duration, and the
     **rights summary** ("12 cleared · 2 restricted");
   - primary is **Send to Cutawan**, with Export beside it.
5. **Library overview** (`/library`):
   - a page grid with a top row of three plain figures (files, shots, hours), not stat cards: `--text-2xl`
     numerals with slate labels and no boxes;
   - **coverage matrix** of place × topic (or edit stage × time of day). Cells use the `--viz-*` ramp with the count
     inside (mono xs). Zero cells are hatched and labelled "gap";
   - every cell is a button that runs the matching search;
   - a toggle switches to a sortable table (the accessible alternative and the default under
     `prefers-contrast: more`);
   - a "Biggest gaps" list ranks empty combinations by how often they are searched for.
6. **Rights and governance** (`/rights`):
   - tabs: *Expiring soon* (default), *Restricted*, *Blocked*, *Unknown*, *Releases*, *Policies*;
   - each is a table with bulk actions (Mark cleared, Set expiry, Block, Attach release);
   - *Policies* holds the agent rule as a read-only statement: "Agents only see shots that are Cleared. This
     can't be changed per token." Plus territory and usage defaults;
   - every change is logged ("Priya blocked 3 shots · 4 Oct 2026, 14:05", with *Undo* for 24 h).
7. **Ingest and processing** (`/ingest`):
   - watched folders (cards are allowed here: one per folder, with path, file count, last scan, and
     *Pause*/*Rescan*);
   - the queue table (§3.23), filterable by stage and state;
   - a DropZone across the page ("Drop files or folders to add them").
8. **Corrections** are not a separate page. They live in the inspector and Shot detail (§3.10), plus a
   **Review queue** under *Library → Needs review*: low-confidence signals across the library in the Log view,
   worked with `Enter` / `Delete` / `E` and auto-advance.
9. **Settings and admin** (`/settings/*`), with a left list for sections:
   - *Appearance* (theme, density, text size, motion);
   - *Playback* (scrub on hover, dwell preview, large hover preview, captions default, timecode format);
   - *Keyboard* (single-key switch, remap table);
   - *Users and roles* (table; roles are Admin, Editor, Contributor, Viewer, Rights manager);
   - *API tokens for agents*: a table with name, scopes, created, last used and expiry. Creating a token shows
     it once in a mono field with *Copy*, and states "Agents using this token only see cleared shots."
   - *Model adapters*: a table with name, task (shots / vision / audio / transcript / embeddings), where it
     runs (**Local** or **Leaves this machine** chip), status and *Test*;
   - *Storage and proxies*;
   - *About*.

---

## 10. Accessibility checklist (definition of done for every component)

- [ ] Every text token on its surfaces passes the §1.1 table (CI: `scripts/check-contrast.ts`).
- [ ] Visible focus ring on every interactive element via `[data-focus-visible]`. Never hidden or clipped by
      `overflow: hidden`, which is why rings use `outline` on the outermost interactive element.
- [ ] Every target is ≥ 24 × 24, and ≥ 44 under `pointer: coarse`.
- [ ] Every drag has a non-drag alternative (listed per component).
- [ ] Single-key shortcuts are scoped to their region and disabled by the master switch.
- [ ] Hover or focus content is dismissible (`Esc`), hoverable and persistent.
- [ ] No autoplay. Reduced motion is honoured (§4).
- [ ] Status changes use `role="status"` / `role="alert"` and are throttled.
- [ ] Media: captions track available, previews muted, player keyboard complete.
- [ ] Tested with axe-core (vitest-axe) per component, Playwright keyboard-only journeys for the 8 user
      stories, VoiceOver (macOS) and NVDA (Windows) smoke passes before release, and 200% zoom and
      320 CSS px reflow checks for non-grid pages.
