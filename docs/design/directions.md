# Design directions

- Status: complete. **Edge Code** is chosen (see §5 and ADR 014)
- Date: 2026-10-04
- Inputs: `docs/design/research.md` (findings F1–F12, principles §11)

## 0. What every direction must do

These are fixed, whatever the look:

- **Desktop first** (Electron), also served as a web app. Laptop and tablet (768–1024) are supported.
- Light and dark themes, **WCAG 2.2 AA** (with 2.4.13 Focus Appearance adopted from AAA), full keyboard
  operation.
- Smooth scrolling through thousands of thumbnails. Hover and scrub previews feel instant. Video preview
  starts in **< 300 ms**.
- The shot is the unit, and timecode in/out is always visible. Every match explains itself. Rights are visible
  where decisions are made.
- A sibling to **Cutawan** (near-monochrome dark, one restrained accent, Lucide icons, Inter-like sans, glassy
  top bar on macOS) without being a clone.

All three directions share the same information architecture: top bar with command/search input, left
filter rail, centre results, right inspector. They differ in concept, typography, colour, density, motion and
the one or two signature ideas each brings. All contrast ratios below were computed with the WCAG 2.x
relative-luminance formula. The script is reproduced in `system.md` §1.1.

---

## 1. Direction A: Edge Code

> *The interface as a camera report printed along the edge of the film.*

### Concept
Film stock carries **edge codes** (Kodak Keykode and similar): small, precise, machine-readable numbers printed
beside every frame so the lab and the edit can find any frame. Edge Code treats Metachlorian the same way. The
footage is the picture, and everything Metachlorian knows about it is printed **beside** it in a precise
typographic strip: timecode, duration, frame rate, aspect, rights. Surfaces are **exactly neutral grey**
(grading suite practice). One accent, **Key**, a chroma-key magenta chosen because it is the colour least
likely to appear in natural footage, marks selection and primary action, and nothing else.

### Rationale
- Answers F11 (calm through restraint) and the grading-suite rule (§7 of research): colour belongs to footage.
- The monospace edge strip makes **timecodes scannable in columns** across a uniform grid (F1, F5).
- Squarer radii, slate labels and hairlines read as "instrument", the opposite of a SaaS card dashboard.
- Magenta is used by almost no NLE or MAM (Premiere blue, Frame.io purple, Resolve orange, FCP yellow), so
  it is distinctive. It is also the most separable selection colour over arbitrary footage.

### Mood references
- **Kodak Keykode edge print** and lab **camera reports and slates**: tiny mono numerals and uppercase labels.
- **The Conversation** (Coppola, 1974) and **Blow Out** (De Palma, 1981): professionals re-examining a
  recording until it gives up its evidence. This is the "why it matched" posture.
- **Wim Crouwel's** grid-led posters and **Experimental Jetset** for typographic restraint. **SBB railway
  timetables** for dense tabular clarity.
- Products: **DaVinci Resolve** scopes and media pool (neutral greys), **Teenage Engineering** manuals
  (mono labels, single accent), **Linear** (calm density), **Raycast** (keyboard first).

### Typography
| Role | Font (open licence) | Package | Notes |
|---|---|---|---|
| UI, headings, descriptions | **Instrument Sans** (OFL) | `@fontsource-variable/instrument-sans` (use the `wdth.css` entry: wght 400–700, wdth 75–100%) | Crisp grotesk with a **width axis**: 100% for reading, 87.5% for dense card titles, 80% for slate labels in tight places. Has `tnum`. |
| Timecode, numerals, slate labels, code | **JetBrains Mono** (OFL) | `@fontsource-variable/jetbrains-mono` (wght 100–800) | Default zero is distinguished from O (checked: 3 contours). Tall x-height (0.55 em) stays legible at 11–12 px. |

### Colour (token sketch; the full set is in `system.md`)
Neutral (R = G = B) surfaces in both themes. **Key** magenta for selection and primary action. Status colours
always come with an icon and a word.

| Token | Dark (default) | Light | Contrast, worst surface (dark / light) |
|---|---|---|---|
| canvas (grid well) | `#141414` | `#e8e8e8` | — |
| panel | `#1a1a1a` | `#f4f4f4` | — |
| raised (inputs, popovers) | `#212121` | `#ffffff` | — |
| hover / pressed | `#2a2a2a` / `#333333` | `#e0e0e0` / `#d6d6d6` | — |
| fg-1 (primary text) | `#ececec` | `#141414` | 10.69 / 12.68 |
| fg-2 (secondary) | `#b4b4b4` | `#434343` | 6.09 / 6.81 |
| fg-3 (tertiary, labels) | `#a0a0a0` | `#545454` | 4.83 / 5.21 |
| border-control (1.4.11) | `#828282` | `#6e6e6e` | 3.29 / 3.51 |
| **key** | `#ff5cc8` | `#a3127a` | 4.58 / 4.94 (text-grade) |
| on-key text | `#1a0012` | `#ffffff` | 7.24 / 7.18 |
| cleared / caution / blocked | `#4cc38a` / `#f0b429` / `#ff6b6b` | `#11663e` / `#754c00` / `#ad1f28` | ≥ 4.55 / ≥ 4.81 |

### Density
High, but quiet. Default thumbnail is 232 px wide (M), with S 168 px and L 320 px. There are 12 px gutters,
32 px controls and 13 px base UI text. At 1440 px with both panels open you see 5 columns × 4 rows = **20
shots above the fold** (M), or 7 × 6 = 42 (S).

### Motion
Fast and mechanical, like a transport control: 80–180 ms, no overshoot, no bounce. There is one continuity
move: the card's frame expands into the inspector player (180 ms) when a shot is opened. Reduced motion
removes it.

### Signature elements
1. **Edge strip** under every frame: `00:14:03:12 ▸ 6s · 25p · 16:9` in mono, rights glyph at the right end.
2. **Slate labels**: mono uppercase section labels (`EDIT STAGE`, `WHY IT MATCHED`).
3. **Key ring**: a 2 px magenta ring **outside** the frame for selection, so it never tints the footage. The
   neutral focus ring sits outside that.
4. **Range bars** on the filmstrip (after FCP): matched shots as bars above the strip, rights restrictions as
   hatching below.
5. **Match-strength rail**: a thin vertical scrubber on the grid's right edge with a tick where matches turn
   weak.

### Sketches

**A1. Search and results (1440 × 900, dark)**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▚ Metachlorian │ ⌕ handheld street food close-ups, busy, night            ⌘K │ ● Local ? ⚙ │
│                │ [shot size close-up ×][camera handheld ×][night ×] street food, busy      │
├────────────────┼─────────────────────────────────────────────────────┬─────────────────────┤
│ FILTERS      « │ 412 shots in 38 files · 0.4 s   Shots|Files  ▦ ☰ ▤  │ SHOT 00:14:03:12  » │
│                │ Size S M L                       Sort: best match ▾ │ ┌─────────────────┐ │
│ EDIT STAGE     │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   ▲ │ │                 │ │
│ ■ Raw    2,103 │ │         │ │▮▮▮▯▯▯▯▯▯│ │         │ │ ░ ░ ░ ░ │   █ │ │  player 16:9    │ │
│ □ Selects  311 │ │         │ │ scrub   │ │         │ │ blocked │   █ │ │                 │ │
│ □ Finished  40 │ └─────────┘ └─────────┘ └─────────┘ └─────────┘   █ │ └─────────────────┘ │
│                │ 01:02:11:04 00:14:03:12 00:02:40:00 00:31:12:18   █ │ ◀◀ ▶ ▶▶  I  O  CC   │
│ RIGHTS         │ 4s 25p   ✓  6s 50p   ◷  3s 25p   ✓  9s 24p   ⊘    █ │                     │
│ ■ Cleared only │                                                   ▒ │ WHY IT MATCHED      │
│                │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   ▒ │ close-up    ▮▮▮▮▯ 91│
│ SHOT           │ │         │ │         │ │  ▐ 9:16 │ │         │   ▒ │ night       ▮▮▮▮▯ 88│
│ □ Close-up  96 │ │         │ │         │ │  ▐      │ │         │   ▒ │ handheld    ▮▮▮▯▯ 74│
│ □ Wide      41 │ └─────────┘ └─────────┘ └─────────┘ └─────────┘   ▒ │ food stall  ▮▮▮▯▯ 70│
│                │ 00:08:21:00 00:51:02:10 00:00:12:03 00:17:44:20   ▒ │ ✎ busy  Sam  human  │
│ TECHNICAL      │ 5s 25p   ✓  2s 25p   ✓  7s 30p   ✓  4s 25p   ✓    ▼ │                     │
│ fps  [24]–[60] │ ───────────── Weaker matches below ─────────────    │ RIGHTS  ✓ Cleared   │
│ codec ProRes ▾ │                                                     │ Release on file     │
├────────────────┴─────────────────────────────────────────────────────┴─────────────────────┤
│ 3 selected   Add to Selects  B   Find similar  S   Send to Cutawan  ⌘⇧E   Export ▾   Clear │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**A2. Shot detail (inspector expanded to a full page with `Enter`)**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ ← Results   Market_Night_A012.mov  ›  Shot 14 of 63              Raw · Cleared ✓   ⋯       │
├──────────────────────────────────────────────────────┬─────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────┐ │ SHOT 14                             │
│ │                                                  │ │ Close-up of hands at a street food  │
│ │                                                  │ │ stall, steam, neon, crowded, night. │
│ │                 player (16:9 well)               │ │                                     │
│ │                                                  │ │ IN 00:14:03:12  OUT 00:14:09:12  6s │
│ │                                                  │ │ 3840×2160 · 50p · ProRes 422 HQ     │
│ └──────────────────────────────────────────────────┘ │ S-Log3 · 10-bit · 16:9              │
│ 00:14:05:02 ◀◀ J  ▶ K  ▶▶ L    I  O    CC   1×  Vol  │                                     │
│ ├┼─────┼──┼───[■■■■■■]──┼────┼─────┼──┼────────────┤ │ SIGNALS                     Edit  E │
│                                                      │ shot size close-up   model  ▮▮▮▮▯ 91│
│ WHY IT MATCHED                                       │ time     night       model  ▮▮▮▮▯ 88│
│ "close-ups" → shot size: close-up (0.91, vision)     │ camera   handheld    motion ▮▮▮▯▯ 74│
│ "night"     → time of day: night (0.88, vision)      │ crowd    busy  ✎ Sam, 2 Oct  human  │
│ "street food" → objects: wok, steam (0.70, vision)   │ place    Bangkok     GPS    ▮▮▮▮▮ 99│
│ "busy"      → crowd: busy (human correction)         │ speech   none        audio          │
│                                                      │                                     │
│ SIMILAR SHOTS                           See all  S   │ RIGHTS                    Change  R │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │ ✓ Cleared for all uses              │
│ │      │ │      │ │      │ │      │ │      │         │ Location release · expires never    │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘         │ Agents: visible                     │
└──────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

**A3. Asset view (one file, shot structure)**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ ← Library   Market_Night_A012.mov       Raw ▾   63 shots · 41:12   Rights: 2 restricted ⚠  │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────┐  FILE                                            │
│ │                                       │  /Volumes/Shoot_04/A012.mov                      │
│ │          player (16:9 well)           │  3840×2160 · 50p · ProRes 422 HQ · S-Log3        │
│ │                                       │  Ingested 2 Oct 2026 · analysed · proxies ready  │
│ └───────────────────────────────────────┘  Camera FX6 · Lens 24–70 · GPS Bangkok           │
│ 00:14:05:02                                                                                │
│ MATCHES   ▬▬▬▬     ▬▬            ▬▬▬▬▬▬               ▬▬▬                  ▬▬              │
│ SHOTS    ┃▓▓▓▓┃▓▓▓▓▓┃▓▓┃▓▓▓▓▓▓▓▓┃▓▓▓┃▓▓▓▓▓▓▓▓▓▓┃▓▓┃▓▓▓▓▓▓▓┃▓▓▓▓┃▓▓▓▓▓▓▓┃▓▓▓┃▓▓▓▓▓▓┃▓▓▓▓▓▓┃ │
│ RIGHTS                     ╱╱╱╱╱╱╱╱                                ╱╱╱╱                    │
│ 00:00     05:00     10:00     15:00     20:00     25:00     30:00     35:00     40:00      │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ #   IN           OUT          DUR  SHOT SIZE MOVEMENT  TIME   TAGS              RIGHTS     │
│ 13  00:13:51:00  00:14:03:11  12s  Medium    Static    Night  stall, queue      ✓ Cleared  │
│ 14▸ 00:14:03:12  00:14:09:12   6s  Close-up  Handheld  Night  wok, steam ✎      ✓ Cleared  │
│ 15  00:14:09:13  00:14:30:02  21s  Wide      Pan L     Night  crowd, signage    ⚠ Faces    │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Direction B: Light Table

> *The picture editor's desk: contact sheets on a light box, marked up in red chinagraph.*

### Concept
Before NLEs, selects were made on a **light table**. Photographers and editors laid out contact sheets and
negatives, looked through a loupe and circled keepers in red grease pencil. Light Table makes Metachlorian
feel like that desk. Results arrive as **contact-sheet strips** (one strip per file, matching shots in
sequence, numbered like frames). A serif carries descriptions and notes. Selections are **red chinagraph
circles**. The default is light, with a warm "darkroom" dark theme.

### Rationale
- The most approachable direction for content and marketing leads, who read more than they scrub.
- Contact-sheet grouping makes **edit stage and sequence** obvious (raw vs selects vs finished) (story 4).
- A serif plus generous margins make "why it matched" and handoff notes pleasant to read.

### Mood references
- **Magnum Contact Sheets** (Thames & Hudson, 2011): grease-pencil selects on real contact sheets.
- **Blow-Up** (Antonioni, 1966): enlarging a contact sheet to find what is in the frame.
- **Criterion Collection** booklets, **The New Yorker** typographic calm, **Kinfolk**'s whitespace.
- Products: **Things 3** (restraint), **Are.na** (material first), **Apple Photos** (light, airy grid).

### Typography
| Role | Font | Package |
|---|---|---|
| Descriptions, headings, notes | **Newsreader** (OFL, opsz 6–72, wght 200–800) | `@fontsource-variable/newsreader` |
| UI | **Hanken Grotesk** (OFL, wght 100–900) | `@fontsource-variable/hanken-grotesk` |
| Timecodes, frame numbers | **IBM Plex Mono** (OFL, static 400/500) | `@fontsource/ibm-plex-mono` |

### Colour
| Token | Light "paper" (default) | Dark "darkroom" | Contrast |
|---|---|---|---|
| paper / board | `#f3efe6` | `#1b1915` | — |
| card | `#fbf9f4` | `#24221d` | — |
| ink-1 | `#1d1b16` | `#ece6da` | 14.99 / 14.12 |
| ink-2 | `#59534a` | `#b8b0a2` | 6.63 / 8.17 |
| ink-3 | `#6b6459` | `#9c9486` | 5.09 (paper) / 5.29 (card) |
| **chinagraph** (accent) | `#b42d1a` | `#ff7a5c` | 5.49 / 6.85; on-accent 6.30 / 6.85 |
| rule (control borders) | `#8a8275` | `#7d766a` | 3.31 / 3.90 |

The **cost**: warm paper surrounds bias colour judgement (research §7), and chinagraph red collides with
"blocked" in rights semantics.

### Density
Medium-low. There are 16 px gutters and 14 px base text, and contact strips show 6–8 small frames per file
row. Above the fold at 1440 px you get about 5 files × 7 frames = 35 frames, but only 5 files' worth of context.

### Motion
Soft and paper-like: 200–280 ms fades and a gentle "loupe" zoom (scale 1 → 1.04) on hover. Chinagraph circles
draw on with an 180 ms stroke animation, which reduced motion removes.

### Signature elements
Contact-sheet strips per file. Chinagraph selection circles. A **loupe** hover that magnifies the frame under
the pointer. Serif "why it matched" sentences. Frame numbers in Plex Mono.

### Sketches

**B1. Search and results**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│  Metachlorian        handheld street food close-ups, busy, night                    Search │
│                      close-up · handheld · night · "street food, busy"      Filters (4) ▾  │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                            │
│   Market_Night_A012 · Raw · 9 matching shots                                    Open file  │
│   ┌────┐ ┌────┐ ╭────╮ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                           │
│   │    │ │    │ │ ◯  │ │    │ │    │ │    │ │    │ │    │ │    │                           │
│   └────┘ └────┘ ╰────╯ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘                           │
│   14:03  14:31  15:02  18:40  19:12  22:05  27:44  31:10  33:58                            │
│                                                                                            │
│   Soi_38_Selects · Selects · 4 matching shots                                   Open file  │
│   ┌────┐ ┌────┐ ┌────┐ ┌────┐                                                              │
│   │    │ │    │ │    │ │    │      "Close-up of hands at a street food stall, steam,       │
│   └────┘ └────┘ └────┘ └────┘       neon, crowded." Matched close-up, night, handheld.     │
│   02:11  02:40  05:18  07:02                                                               │
│                                                                                            │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│  2 circled  ·  Add to selects  ·  Send to Cutawan  ·  Export                               │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**B2. Shot detail**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│  ← Back to contact sheets                                                                  │
│                                                                                            │
│   ┌────────────────────────────────────────────────┐   Close-up of hands at a street       │
│   │                                                │   food stall, steam, neon, crowded.   │
│   │                    player                      │                                       │
│   │                                                │   Shot 14 · 00:14:03:12 – 09:12       │
│   └────────────────────────────────────────────────┘   Raw · Cleared for all uses          │
│   ────────────●──────────────────────────────────                                          │
│                                                        Why it matched                      │
│   Signals                                              Your words "close-ups" and "night"  │
│   Close-up ............................ very likely    matched what the picture shows;     │
│   Night ............................... very likely    "busy" matched a note Sam added.    │
│   Busy ............................ added by Sam                                           │
│                                                        Similar shots                       │
│                                                        ┌────┐ ┌────┐ ┌────┐ ┌────┐         │
│                                                        └────┘ └────┘ └────┘ └────┘         │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**B3. Asset view**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│  Market_Night_A012 · Raw · 63 shots · 41 minutes                                           │
│                                                                                            │
│   01     02     03     04     05     06     07     08     09     10     11     12          │
│   ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐      │
│   └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘      │
│   13     14     15     16     17     18     19     20     21     22     23     24          │
│   ┌────┐ ╭────╮ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐      │
│   └────┘ ╰────╯ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘      │
│   ...                                                                                      │
│   Notes on this file                                                                       │
│   Shot on the night market walk, 2 Oct. Faces in 15–18 need releases.                      │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Direction C: Night Shift

> *A cinematic, spatial control room: glass panes floating over the footage itself.*

### Concept
Push Cutawan's macOS glass further. The background is a heavily blurred, darkened version of the focused
shot. Panels are **frosted glass**, and the accent is **scope cyan**, the trace colour of a waveform monitor.
Search is a large hero field. Results can switch from a grid to a **similarity map**: a zoomable canvas where
shots cluster by visual likeness (after Cosmos clusters), so "find similar" becomes "look nearby". Motion is
expressive, with shared-element flights between grid, map and detail.

### Rationale
- The most "wow" in a demo and the closest sibling to Cutawan's glass.
- The similarity map is a genuinely new answer to story 2 (find similar).
- It suits the "street food, night" footage the product is often shown with.

### Mood references
- **Collateral** (Michael Mann, 2004) and **Blade Runner 2049** (Deakins): sodium and cyan night.
- **Waveform and vectorscope** traces. **Cosmos** (calm dark visual clusters). **Arc** (glass, gradients).
- Products: **Cutawan** (glass top bar), **Raycast** (dark, sharp), **Apple Vision Pro** glass materials.

### Typography
| Role | Font | Package |
|---|---|---|
| Display (hero search, titles) | **Bricolage Grotesque** (OFL, opsz 12–96, wdth 75–100, wght 200–800) | `@fontsource-variable/bricolage-grotesque` |
| UI | **Onest** (OFL, wght 100–900) | `@fontsource-variable/onest` |
| Timecodes | **Martian Mono** (OFL, wdth 75–112.5, wght 100–800) | `@fontsource-variable/martian-mono` |

### Colour
| Token | Dark "night" (default) | Light "dawn" | Contrast |
|---|---|---|---|
| void / page | `#0b0e14` | `#f2f5f9` | — |
| glass (approximate solid) | `#161b24` at 72% + blur 24 px | `#ffffff` at 80% + blur | — |
| text-1 | `#e6ecf5` | `#0e1420` | 16.26 / 16.85 |
| text-2 | `#9aa6b8` | `#46526a` | 7.84 / 7.18 |
| text-3 | `#8592a6` | `#5a6680` | 5.47 (on glass) / 5.76 |
| **scope cyan / teal** | `#3ee6d0` | `#00796b` | 12.36 / 4.87; on-accent 12.36 / 5.32 |
| control borders | `#56627a` | `#7b879c` | 3.15 / 3.32 |

The **cost**: glass contrast depends on what is behind it (the solid fallback must be what we test). The
blue-tinted surround biases colour. Cyan clashes with teal-and-orange graded footage.

### Density
Low to medium. Large 280 px cards, 20 px gutters, and a hero search that takes 160 px of height. About 12 shots
above the fold.

### Motion
Expressive: 240–400 ms spring flights between views, parallax on the backdrop, the map zooming toward a
cluster. Reduced motion falls back to cross-fades, but the map is inherently motion-heavy.

### Signature elements
Blurred live backdrop. Similarity map. Hero search. Shared-element flights.

### Sketches

**C1. Search and results (similarity map mode)**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│░░░░░░░░░░░░░░░░░░░░░░░░░ blurred backdrop of focused shot ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│░░  ╭──────────────────────────────────────────────────────────────────────────────────╮  ░░│
│░░  │  handheld street food close-ups, busy, night                              ⌘K     │  ░░│
│░░  ╰──────────────────────────────────────────────────────────────────────────────────╯  ░░│
│░░        Grid   ·  Map   ·  Files              412 shots                                 ░░│
│░░                                                                                        ░░│
│░░      ┌───┐ ┌───┐                         ┌───┐                                         ░░│
│░░      └───┘ └───┘  ┌───┐   "stalls"       └───┘ ┌───┐  "crowds"                         ░░│
│░░    ┌───┐ ┌───┐    └───┘                  ┌───┐ └───┘ ┌───┐                             ░░│
│░░    └───┘ └───┘ ┌───┐            ┌───┐    └───┘ ┌───┐ └───┘                             ░░│
│░░                └───┘   ┌───┐    └───┘          └───┘                                   ░░│
│░░        "woks + steam"  └───┘  ┌───┐      "neon signage"                                ░░│
│░░                               └───┘                                                    ░░│
│░░  ╭────────────────────────────────╮                                                    ░░│
│░░  │ glass inspector · shot 14      │                                                    ░░│
│░░  ╰────────────────────────────────╯                                                    ░░│
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**C2. Shot detail**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ backdrop: this shot, blurred ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│░░  ╭──────────────────────────────────────────────────────╮ ╭───────────────────────────╮ ░│
│░░  │                                                      │ │ Close-up · night · busy   │ ░│
│░░  │                  player (large)                      │ │ 00:14:03:12  6s  50p      │ ░│
│░░  │                                                      │ │                           │ ░│
│░░  ╰──────────────────────────────────────────────────────╯ │ ◉ close-up       91%      │ ░│
│░░   ━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │ ◉ night          88%      │ ░│
│░░                                                           │ ◉ busy  (Sam)             │ ░│
│░░   Nearby in the map →  ┌───┐ ┌───┐ ┌───┐ ┌───┐            │ Cleared ✓                 │ ░│
│░░                        └───┘ └───┘ └───┘ └───┘            ╰───────────────────────────╯ ░│
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**C3. Asset view**
```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│░░  Market_Night_A012                                       ╭────────────────────────╮    ░░│
│░░  ╭──────────────────────────────────────────────╮         │ 63 shots · 41:12       │   ░░│
│░░  │                  player                      │         │ Raw · 2 restricted     │   ░░│
│░░  ╰──────────────────────────────────────────────╯         ╰────────────────────────╯   ░░│
│░░  ╭──────────────────────────────────────────────────────────────────────────────────╮  ░░│
│░░  │ ▇▇▅▅▇▇▇▃▃▇▇▇▇▇▅▅▅▇▇▃▃▇▇▇▇▇▇▅▅▇▇▇▃▃▃▇▇▇▇▅▅▇▇▇  glowing shot ribbon (cyan = match) │  ░░│
│░░  ╰──────────────────────────────────────────────────────────────────────────────────╯  ░░│
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Evaluation

Scores run from 1 (poor) to 5 (excellent). Weights reflect the brief: shot-level search, rights and
performance first. The maximum is 170.

| # | Criterion | Weight | A Edge Code | B Light Table | C Night Shift | Notes |
|---|---|---|---|---|---|---|
| 1 | **Story: NL search → shot-level results with thumbnails, previews, timecodes** | 3 | 5 | 4 | 4 | A's edge strip shows TC, duration and fps on every card in aligned columns. B hides TC detail inside contact strips. C's cards are large but few. |
| 2 | **Story: select a shot and find similar** | 2 | 4 | 3 | 5 | C's map is the most novel. A re-seeds the grid in place with `S` plus a breadcrumb, which is fast and keyboard-able. B goes to a detail page. |
| 3 | **Story: filter by resolution, fps, aspect, log, duration** | 2 | 5 | 3 | 3 | A has a dense rail with numeric inputs. B collapses filters into a menu. C has nowhere calm to put a rail. |
| 4 | **Story: raw, selects or finished edit at a glance** | 1 | 5 | 4 | 3 | A has a role facet and a role label in the inspector header and asset view. B's strips imply sequence but not role. C shows it only in the glass panel. |
| 5 | **Story: mark rights, releases, expiry; results respect them** | 3 | 5 | 4 | 3 | A puts a rights glyph and word on every card, hatched ranges on the filmstrip, and status colours on neutral grounds. B's accent red collides with "blocked". C's cyan on glass weakens status colours. |
| 6 | **Story: agent gets only cleared shots** (admin clarity) | 2 | 5 | 4 | 3 | A's instrument aesthetic suits the token and scope tables. C's glass tables are hard to read. |
| 7 | **Story: hand shots to Cutawan as a package** | 2 | 4 | 5 | 3 | B's reading layout makes the handoff note lovely. A's selection bar plus package dialog is clear. C's flight animations add nothing. |
| 8 | **Story: correct a wrong tag and it sticks** | 2 | 5 | 4 | 3 | A's signal row has source, confidence and an inverse "human" marker, with `E` to edit inline. B uses prose. C uses dots. |
| 9 | Calm at density (thousands of thumbnails) | 3 | 5 | 3 | 3 | A is uniform with hairlines and one accent. B's grouping gives few files per screen. C's backdrop and blur are visually busy. |
| 10 | Accessibility risk (contrast, focus over media, keyboard, reduced motion) | 3 | 5 | 4 | 2 | A's rings sit off the footage on solid neutral surfaces. C's glass contrast varies with content and the map is weak for AT and keyboard. |
| 11 | Performance risk (60 fps scroll, < 300 ms preview) | 3 | 5 | 4 | 2 | `backdrop-filter` over a virtualised grid is expensive. The live backdrop decodes an extra video. |
| 12 | Colour-critical viewing (neutral surround) | 2 | 5 | 2 | 2 | Only A is chroma-neutral. B is warm and C is blue. |
| 13 | Differentiation (not a generic dashboard or template) | 2 | 4 | 5 | 5 | A risks reading as "just pro software". Its magenta key, edge strip and slate labels carry the identity. |
| 14 | Sibling fit with Cutawan | 1 | 4 | 2 | 5 | A shares near-monochrome, Lucide and a dark default, but is squarer and has a light theme. |
| 15 | Light/dark parity | 2 | 5 | 4 | 2 | A's themes are generated from the same neutral ramp. C's light theme is an afterthought. |
| 16 | Build cost | 1 | 4 | 4 | 2 | C needs a canvas map, blur fallbacks and a motion system. |
| | **Weighted total (max 170)** | 34 | **162** | 127 | 104 | |

### Sensitivity
- If **differentiation** were tripled (weight 6), A would still lead: 178 vs B 147 vs C 124.
- If performance and accessibility were ignored (weights 0), A would still lead: 132 vs B 103 vs C 92.
- C overtakes A only if "find similar" and demo impact outweigh everything else, which the brief does not
  support.

## 5. Choice: **Edge Code**, with two borrowings

**Edge Code** wins on the stories that matter most (shot-level search, rights, corrections, technical
filters) and on the non-negotiables (accessibility, performance, neutral surround). Its weakness is that it
could feel austere to content and marketing leads. Two borrowings address that:

1. **From Light Table: reading typography for prose.** The *Why it matched* explanation, shot descriptions,
   collection notes and the Cutawan handoff note use Instrument Sans at full width, 14/22, with a 64-character
   measure. This is the "reading mode" of the system. The *Files* grouping in results uses B's contact-sheet
   strip layout (one row per file, matching shots in sequence).
2. **From Night Shift: one continuity flight.** Opening a shot expands its frame into the inspector player
   (180 ms, removed under reduced motion). The similarity *map* is rejected for now (ADR 014, "Revisit when").

The full specification is in `docs/design/system.md`, and the tokens are in `app/src/styles/tokens.css`.
