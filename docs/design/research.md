# Design research: how professionals browse and select footage

- Status: complete (input to `directions.md`, ADR 013 and ADR 014)
- Date: 2026-10-04
- Author: design research lead (build agent)

## 0. Method and limits

This review covers NLE browsers, media asset managers (MAMs), stock libraries, photo libraries and a set of
"calm, fast" creative tools. For each it notes what works, what frustrates people and why, then pulls out
the patterns Metachlorian should copy, change or avoid.

Sources are product documentation, independent reviews, forum threads and engineering write-ups found by web
search on 2026-10-04. Several primary pages (w3.org, linear.app, medium.com) could not be fetched from the
research sandbox because the egress proxy blocked them. Claims from those pages are cited through the search
results that quoted them. WCAG success criteria are summarised from the WCAG 2.2 Recommendation. Library
versions in ADR 013 were read directly from the npm registry on the same day.

Throughout, **shot** means a contiguous range inside a file with its own signals (what Metachlorian indexes).
**Asset** or **file** means the source media. **Clip** is used only when quoting other products.

---

## 1. Summary: twelve findings that shape the design

| # | Finding | Implication for Metachlorian |
|---|---|---|
| F1 | Every serious NLE is converging on natural-language search over *moments*, not files: Premiere Pro's Search panel, Resolve 21's IntelliSearch "Segments" mode, Apple Photos' "scenes within videos", Jumper. | Results are **shots with in/out timecodes** by default. Whole files are a grouping, not the unit. |
| F2 | Accuracy, not features, decides trust. In an independent 46-query benchmark Jumper scored 84/92, Premiere Pro 68, Peakto 51 and Final Cut Pro 12. | Show **why it matched** on every result and make the evidence inspectable, so people can tell a poor match apart from a poor query. |
| F3 | Hover-scrub is loved (FCP skimming, Resolve, Premiere) **and** hated when it is slow, fires by accident or hijacks the viewer. | Scrub from a **sprite sheet**, not video decode. Start scrubbing only after the pointer actually moves inside the thumbnail. Never move the main viewer on hover. Give it an off switch. |
| F4 | Thumbnail generation latency is the number one complaint in Premiere icon view (5–10 s waits). | Thumbnails and sprites are produced at ingest, before an asset is searchable. The UI never waits on decode to draw a grid. |
| F5 | Range-based marks drawn on the filmstrip (FCP's green favourite, red reject and blue keyword bars) are the clearest way to show "which part of this file matters". | The asset filmstrip draws shot boundaries and matched ranges as bars along the strip. |
| F6 | Smart collections and saved searches that store the **query, not the results** (iconik, FCP, Resolve, Frame.io V4 Collections) are what keep large libraries usable. | Saved searches are first-class and URL-addressable. Collections can be static (selects) or smart (saved query). |
| F7 | Stock sites prove that technical and licence filters are table stakes (resolution, fps, duration, model/property release), and users complain when codec, alpha or log are missing. | The filter rail includes codec, bit depth, log/gamma, alpha and edit stage (raw, selects, finished), plus **rights as a filter that cannot be bypassed**. |
| F8 | "More like this" or "Visually similar" from any result is the most-used escape hatch when keyword search fails (Storyblocks, Shutterstock, Getty, Cosmos). | **Find similar** is one keystroke from any shot (`S`) and also accepts a dropped frame or still. |
| F9 | Status and governance buried in a metadata panel is a regression people notice (Frame.io V4 statuses). | Rights state shows **on the card**, in text and shape, not only in the inspector. |
| F10 | Keyboard culling (Lightroom P/X/U with auto-advance; editor J/K/L, I/O, Space) is what makes thousands of items manageable. | Metachlorian adopts editor muscle memory as-is, adds Lightroom-style auto-advance, and stays WCAG 2.1.4 compliant. |
| F11 | Calm comes from restraint: one accent, neutral surfaces, typographic hierarchy, no engagement chrome (Linear, Things, Are.na, Cosmos). For footage, colour grading practice adds a hard rule: neutral grey surrounds so the UI does not bias colour judgement. | Neutral (chroma 0) greys and a single accent that rarely appears in footage. Colour belongs to the footage. |
| F12 | Floating or unconventional chrome costs heavy users time (Figma UI3 reversed floating panels; Arc needs 1–2 weeks of adjustment). | Use fixed, resizable, collapsible panels. Familiar three-pane NLE geometry, with the novelty spent on search and evidence. |

---

## 2. Non-linear editors

### 2.1 Adobe Premiere Pro (Project panel, Search panel)

**What works**
- **Hover scrub** in Icon view plays a clip in its thumbnail as the pointer moves across it, without selecting
  it ([PremiumBeat](https://www.premiumbeat.com/blog/premiere-pro-hover-scrub/),
  [ProVideo Coalition](https://www.provideocoalition.com/tool-tip-tuesday-for-adobe-premiere-hover-scrub/)).
- **Media Intelligence + Search panel** (25.2, 2025). On-device models find people, objects, locations and
  camera angles. Natural-language queries ("close up of person running at sunset") run alongside transcript
  text and embedded metadata such as shoot date or camera, and return "relevant moments you can quickly scrub
  through or load in the Source monitor". Analysis is local, needs no internet and is not used for training
  ([Adobe help](https://helpx.adobe.com/premiere/desktop/organize-media/file-organization/search-for-media-using-ai-powered-media-intelligence.html),
  [No Film School](https://nofilmschool.com/adobe-media-intelligence),
  [How-To Geek](https://www.howtogeek.com/premiere-pro-visual-search-and-caption-translations/)).
- Universal editor keys: **J/K/L** shuttle (tap repeatedly to go faster), **I/O** mark in/out, **Space** to
  play or stop ([Adobe shortcuts](https://helpx.adobe.com/premiere/desktop/get-started/keyboard-shortcuts/default-keyboard-shortcuts.html),
  [No Film School on J/K/L](https://nofilmschool.com/2018/10/how-use-j-k-and-l-keys-premiere-pro-speed-your-workflow)).

**What frustrates people, and why**
- Thumbnails take **5–10 seconds** to appear in Icon view, and again after scrolling. Generation is lazy and
  tied to decode ([Adobe community](https://community.adobe.com/questions-729/premiere-pro-is-extremely-slow-in-generating-thumbnails-in-icon-view-1411128)).
- Hover-scrubbing proxies stalls with spinning cursors, and **accidental scrubbing** jumps the playhead
  when people only meant to move the pointer across the grid
  ([Adobe community: "Stop scrubbing in clip bin"](https://community.adobe.com/questions-729/stop-scrubbing-in-clip-bin-1413124)).
  The usual fix is to switch hover scrub off entirely, which loses the benefit.
- Scroll-to-zoom in the Program panel annoyed people because a passive gesture changed state
  ([Adobe ideas](https://community.adobe.com/t5/premiere-pro-ideas/make-it-stop-please-scroll-wheel-in-program-panel-zooms-in-super-annoying-amp-dumb-new-feature/idi-p/14701157)).

**Take:** make scrubbing instant (pre-rendered sprites) and intentional (pointer movement inside the frame
only). Passive gestures must not change persistent state.

### 2.2 DaVinci Resolve (Media Pool, Smart Bins, IntelliSearch)

**What works**
- Media Pool **Thumbnail, List and Metadata views**. Since v17 a hover scrub on any item shows a live preview
  ([Blackmagic, Resolve 17 announcement](https://www.streetinsider.com/Business+Wire/Blackmagic+Design+Announces+DaVinci+Resolve+17/17575406.html),
  [Resolve manual excerpt](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part474.htm)).
- **Smart Bins** use rules over resolution, codec, frame rate, camera, date, keywords or any field, and stay
  current as media is added. The inspector exposes 200+ metadata fields with custom metadata views
  ([Resolve Club](https://davinciresolveclub.com/davinci-resolve-smart-bins-power-bins/),
  [Cutsio](https://cutsio.com/blog/davinci-resolve-smart-bins-power-bins-media-page)).
  A "Usage = 0" smart bin is a well-known trick for finding unused media
  ([ClipSweeper](https://clipsweeper.com/blog/find-unused-media-davinci-resolve)).
- **IntelliSearch (Resolve 21 Studio)** searches objects, people, faces and dialogue in plain language. It has
  an explicit choice between **Full Clips** and **Segments**, the latter narrowing results to the matching
  portion ([Larry Jordan](https://larryjordan.com/articles/the-power-of-intellisearch-in-davinci-resolve-21/),
  [Cutsio](https://cutsio.com/blog/davinci-resolve-21-intellisearch-search-media-by-content)).

**What frustrates people, and why**
- The dark UI cannot be re-themed. Forum users ask for a lighter grey, but Blackmagic keeps it dark because of
  its grading roots: a bright frame around the image biases perception of the image
  ([Blackmagic forum](https://forum.blackmagicdesign.com/viewtopic.php?amp=&p=714163&t=131713)).
- 200 fields is power without guidance. Most people never configure a metadata view.

**Take:** shot-level ("segments") results by default, with a "group by file" toggle. Ship opinionated default
metadata views per role instead of a blank field picker. Offer a light theme, but keep a neutral grey well
behind the footage in both themes.

### 2.3 Final Cut Pro (Browser, skimming, keywords)

**What works**
- **Skimming** (`S` toggles it). Moving the pointer over any filmstrip previews it in the viewer. **Skimmer
  Info** (`Ctrl-Y`) shows source timecode and keywords at the skim point
  ([Larry Jordan](https://larryjordan.com/articles/secrets-of-the-final-cut-pro-x-browser/),
  [Apple: analysis keywords](https://support.apple.com/guide/final-cut-pro/view-analysis-keywords-ver64e70ab3/mac)).
- **Range-based tagging drawn on the filmstrip.** Green for favourite, red for rejected and blue for keyword
  ranges run along the top edge of each filmstrip. `F` marks a favourite
  ([Apple: browser views](https://support.apple.com/en-au/guide/final-cut-pro/verd00d3ae7/mac),
  [Apple: select ranges](https://support.apple.com/guide/final-cut-pro/select-ranges-ver28cca92/mac)).
- **Keyword Collections** are pointers, not copies, so one clip can live in many. Keywords can be bound to
  hotkeys for rapid logging. **Smart Collections** (All Video, Favourites and others) update live
  ([Apple: add keywords](https://support.apple.com/guide/final-cut-pro/add-keywords-ver68416335/mac),
  [Apple: Smart Collections](https://support.apple.com/guide/final-cut-pro/organize-smart-collections-ver7a77eb6c/mac),
  [PremiumBeat](https://www.premiumbeat.com/blog/final-cut-pro-x-tutorial-automatic-keyword-collections/)).

**What frustrates people, and why**
- Built-in content search is weak: 12 of 92 points in the
  [ProVideo Coalition / Jumper benchmark](https://www.provideocoalition.com/review-ai-driven-video-search-with-jumper/).
  Organising works well, finding does not.
- Skimming in the main viewer means passing the pointer over the browser disturbs what you were looking at.
- The browser shows clips in a library and has no cross-library view
  ([Creative COW](https://creativecow.net/forums/thread/is-there-any-way-to-have-the-browser-show-just-the/)).

**Take:** copy the range bars and pointer-based collections. Keep skim preview *inside the card* and never
hijack the main player. Search across the whole library by default.

### 2.4 Avid Media Composer (bins)

**What works**
- Three bin views that have hardly changed in decades: **Text** (metadata columns), **Frame** (thumbnails
  that can be dragged into clusters by story beat) and **Script** (a frame plus free-text notes for logging)
  ([ProVideo Coalition](https://www.provideocoalition.com/letsedit13-binviewmodes/),
  [Frame.io Insider](https://blog.frame.io/2024/01/03/organize-your-avid-media-composer-project-by-story-beats/)).
- ScriptSync links the transcript to takes ([Avid](https://www.avid.com/products/media-composer-scriptsync-option)).

**What frustrates people, and why**
- Dense, dated chrome with steep learning. Frame view has no hover preview, so you load each clip to see it.

**Take:** the three views map directly to Metachlorian's **Grid** (Frame), **List** (Text) and **Log** (Script:
thumbnail plus description and transcript) views. Editors already know this mental model.

---

## 3. Media asset managers and AI search tools

### 3.1 iconik
- **Works:** a prominent quick-search bar plus detailed filters. AI enrichment at ingest (transcripts, faces,
  objects) lets you "jump directly to the right asset or moment". **Saved searches store the query, not the
  results**, support relative dates, and can be targets for bulk actions such as transfer, archive and ACL
  changes ([iconik search help](https://app.iconik.io/help/pages/search/),
  [Saved search](https://app.iconik.io/help/pages/search/savedsearch),
  [iconik MAM](https://www.iconik.io/media-asset-management)).
- **Frustrates:** "The search feature is very clunky and convoluted". A steep learning curve for advanced
  features. Slow loading with large high-resolution files, and slow preview and proxy generation
  ([G2 reviews](https://www.g2.com/products/iconik/reviews),
  [Shade comparison](https://shade.inc/blog/iconik-review-video-production)).
- **Take:** one search field that accepts both natural language and structured tokens. Bulk actions on saved
  searches. Proxies ready before an asset is shown as searchable.

### 3.2 CatDV
- **Works:** a detail panel for logging (name, keywords, five-star rating, in/out points). A **Markers tab**
  shows all event markers in a filterable, editable table with highlighted matches
  ([CatDV 14 reference](http://www.squarebox.com/download/CatDVManual.html),
  [Quantum: Use CatDV](https://qsupport.quantum.com/kb/flare/Content/HSeries/H4000E/DocSite/CatDV/UseCatDV.htm?TocPath=Operate+and+Replace%7CUse+CatDV%7C_____0)).
- **Frustrates:** a heavy, form-like UI that looks like a database front end. Still, iconik users cite
  CatDV's remote query as "how search should work" (G2, above). Power users value expressive queries.
- **Take:** a table view of signals per shot that can be filtered and edited inline (Corrections). Expose an
  advanced query syntax for power users without forcing it on anyone.

### 3.3 Axle AI
- **Works:** on-premises AI covering scene understanding, semantic vector search, faces, logos, OCR and
  speech, all running locally so media stays private. Its search lives as a **panel inside Premiere** with
  "simple relevance sliders" ([Axle AI](https://www.axle.ai/),
  [Intellyx](https://intellyx.com/2025/10/22/axle-ai-meaningful-meta-search-of-high-volume-media-assets/),
  [SHOOTonline](https://www.shootonline.com/spw/axle-ai-announces-ai-powered-media-search-software-with-data-privacy/)).
- **Take:** privacy is a selling point and must be **visible**. The "content leaves this machine" indicator
  is a core component, not a footnote. Relevance needs a visible, adjustable threshold.

### 3.4 Frame.io V4
- **Works:** 33 built-in metadata fields plus custom fields (10 field types) stored at account level.
  **Collections** are smart folders driven by metadata (rating, assignee, status, platform). Card display can
  be customised (aspect ratio, which fields show)
  ([Frame.io help: metadata](https://help.frame.io/en/articles/9092149-getting-started-how-do-i-use-metadata),
  [Frame.io blog](https://blog.frame.io/2024/10/14/frame-io-v4-the-fully-reimagined-platform-is-now-available-for-all/),
  [CineD](https://www.cined.com/new-frame-io-version-4-introduced-with-multi-panel-customization-metadata-frameworks-and-more/)).
- **Frustrates:** statuses moved out of the top bar into the metadata panel, which reviewers call "a big step
  backwards" because clients will not dig for them. The forced V3→V4 migration broke pipelines, and custom
  metadata was unreadable through the API until account-level migration
  ([Trustpilot](https://www.trustpilot.com/review/frame.io),
  [Frame.io forum](https://forum.frame.io/t/forced-migration-to-frameio-v4-will-break-my-entire-companys-pipeline/3190),
  [ALM thread](https://forum.frame.io/t/custom-metadata-fields-unreadable-via-v4-api-requesting-priority-migration-to-account-level-metadata/3418)).
- **Take:** governance state (rights, role) lives **on the card**. Everything the UI shows must also be
  available through the agent API (agents are first-class users).

### 3.5 Jumper (plugin and standalone)
- **Works:** fully local. It searches about 100 hours of footage in about 0.2 s once indexed, analyses faster
  than real time, runs inside Premiere, Resolve, Avid and FCP, and won the independent benchmark above
  ([getjumper.io](https://getjumper.io/), [Jumper FAQ](https://docs.getjumper.io/faq),
  [ProVideo Coalition review](https://www.provideocoalition.com/review-ai-driven-video-search-with-jumper/)).
- **Take:** the bar for "instant" is set. Search results must render the first screen in well under a second.
  The design budget assumes server time ≤ 250 ms (see `system.md` §6).

---

## 4. Stock footage libraries

| Product | What works | What frustrates | Source |
|---|---|---|---|
| **Artgrid** | Search by Video Themes, **Shot Types** and People. Shot-type filters for framing, camera movement and format, combinable. Hover preview on thumbnails. A clean UI without bloat. | Filtering depth is uneven across categories (reviews disagree). | [Jonny Elwyn](https://jonnyelwyn.co.uk/film-and-video-editing/the-best-high-end-stock-video-footage-sites-compared/), [Photutorial](https://photutorial.com/artgrid-review/), [Artgrid help](https://artgrid.zendesk.com/hc/en-us/articles/8069563020701-How-to-Find-Download-and-Use-Footage) |
| **Storyblocks** | Filters for resolution (HD/4K/8K), frame rate (23.98 to 59.94), duration, usage rights, **model released / property released only**. "More like this" on hover. | Relevance decays after about page 5, with "increasingly irrelevant results". **No codec or alpha filter**, so you open each clip to check. | [Photutorial](https://photutorial.com/storyblocks-review/), [Experte](https://www.experte.com/stock-photos/storyblocks), [Storyblocks help](https://help.storyblocks.com/en/articles/3622286-what-are-the-specifications-of-your-video-clips) |
| **Pond5** | Huge catalogue and a dedicated video search engine. | "Lack of search filters makes finding what you need tough". Off-topic results. | [Experte](https://www.experte.com/stock-photos/pond5), [Pond5 blog](https://blog.pond5.com/28346-video-search-engine-pond5/) |
| **Shutterstock** | **Reverse image search for video** (upload a frame or still). "Visually similar" (colour, temperature, subject) and "Same model" rails on clip pages. Power-user advice is to start from keywords and pivot through similar. | Similar rails sit below the fold on a separate page, so pivoting costs a page load. | [Shutterstock press](https://www.shutterstock.com/press/11570), [Shutterstock blog](https://www.shutterstock.com/blog/finding-best-stock-footage), [Reverse search for video](https://www.shutterstock.com/blog/reverse-image-search-for-video) |
| **Getty Images** | "Search by image or video" in the search box. Very deep filters. Editorial vs creative licensing is explicit. | Filter depth becomes a wall of checkboxes. | [Shutterstock help comparison / Getty](https://www.shutterstock.com/help/en/articles/10617040-searching-for-video-clips), [Search Engine Journal](https://www.searchenginejournal.com/best-image-search-engines/299963/) |

**Take:**
1. **Releases and usage rights are filters**, and for agents they are hard constraints, not preferences.
2. Ship the technical facets stock sites miss: codec, bit depth, log/gamma curve, alpha, HDR, edit stage.
3. Find similar works **in place** (the results grid re-seeds) with a breadcrumb back, not on a detail page
   below the fold.
4. Relevance must not silently decay. Show a visible **match-strength divider** ("Weaker matches below")
   instead of endless pagination.

---

## 5. Photo libraries

### 5.1 Lightroom Classic
- `G` for Grid, `E` for Loupe. Flags are **P** (pick), **X** (reject), **U** (unflag). With **Caps Lock** on,
  or with `Shift+P`, `Shift+X` and `Shift+U`, each flag **auto-advances** to the next photo. This is the fastest
  culling loop in any mainstream tool
  ([Adobe shortcuts](https://helpx.adobe.com/lightroom-classic/help/keyboard-shortcuts.html),
  [Photofocus](https://photofocus.com/photography/lightroom-shortcuts-for-faster-culling/),
  [Fstoppers](https://fstoppers.com/lightroom/keyboard-shortcuts-actually-speed-lightroom-classic-718346)).
- **Frustration:** users ask for up/down arrow culling customisation
  ([Adobe ideas](https://community.adobe.com/t5/lightroom-classic-ideas/p-set-up-down-arrows-keyboard-shortcuts-for-culling/idi-p/13444892)).
- **Take:** `Shift+` variants of selection and collection actions advance focus. Shortcuts can be remapped
  (this also satisfies WCAG 2.1.4).

### 5.2 Apple Photos
- Natural-language search ("Maya skateboarding in a tie-dye shirt") covers photos **and specific scenes inside
  videos**, with **smart completion suggestions** while typing and a Filter menu (Favourites, Edited, Photos,
  Videos and more) ([Apple support](https://support.apple.com/guide/mac-help/use-apple-intelligence-in-photos-mchl35c53342/15.0/mac/15.0),
  [MacRumors](https://www.macrumors.com/how-to/ios-use-natural-language-search-photos/),
  [Apple: search](https://support.apple.com/guide/photos/search-for-photos-and-videos-pht64de33e5a/mac)).
- **Frustration:** semantic search gives no explanation. When it misses, people cannot tell why
  ([Apple discussions](https://discussions.apple.com/thread/256196604)).
- **Take:** completion suggestions should come from the library's own vocabulary (places, people, tags), and
  every result should explain its match.

### 5.3 Google Photos (web)
- Engineering goals: **justified full-width layout, aspect ratio preserved, scrubbable to any point in the
  archive, hundreds of thousands of items, 60 fps, near-instant load**. Space is **pre-allocated** so the
  scrollbar represents the whole archive. The grid is split into sections and segments so only a few hundred
  items are laid out at once (2–3 ms)
  ([Harasymiv, "Building the Google Photos Web UI"](https://medium.com/google-design/google-photos-45b714dfbed1), via
  [HN discussion](https://news.ycombinator.com/item?id=17510566)).
- **Take:** pre-allocate scroll height from the result count. Add a **position scrubber** (match strength,
  date or timecode) to the right of the grid. Lay out in sections.
  Metachlorian uses **uniform 16:9 cells** rather than justified rows (§8.2) because footage is mostly 16:9,
  uniform cells give true rows and columns for arrow keys, and timecodes then line up.

### 5.4 Eagle
- Search by **dominant colour**, shape, size, dimensions, tags, rating and annotation, with smart folders from
  tags ([Eagle blog](https://en.eagle.cool/blog/post/how-to-organize-media-library),
  [Tuts+](https://webdesign.tutsplus.com/organize-design-assets-with-eagle-app--cms-36971t)).
- **Take:** colour and look are legitimate facets for footage (night, sodium-lit, teal shadows). Expose a
  **colour** facet derived from shot analysis.

---

## 6. Creative and product tools (how calm, fast UIs are made)

| Tool | Pattern worth copying | Caution | Source |
|---|---|---|---|
| **Linear** | Themes are **generated in LCH** from three inputs (base, accent, contrast) rather than 98 hand-set variables. A contrast input gives high-contrast themes for free. Selected and elevated subtrees regenerate the theme against their own background. A later refresh aimed at "a calmer interface". | Generated themes need a contrast gate. Perceptual uniformity is not WCAG compliance. | [Linear: redesign part II](https://linear.app/now/how-we-redesigned-the-linear-ui), [Linear: calmer interface](https://linear.app/now/behind-the-latest-design-refresh) |
| **Raycast** | Keyboard first: the input keeps focus and arrows move an `aria-activedescendant` highlight. Search is the first step of an action ("find, then act"). Density as a feature, monospace accents to signal "tool". | Pure keyboard-first UIs hide affordances from pointer users. | [setproduct command palette guide](https://www.setproduct.com/blog/command-palette-ui-design-guide), [Raycast DESIGN.md (community)](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/raycast/DESIGN.md) |
| **Figma UI3** | Collapsible panels give the canvas the space. Properties are re-prioritised by task. | **Floating panels were reverted** after beta because they slowed heavy users and cramped small screens. | [Figma: behind UI3](https://www.figma.com/blog/behind-our-redesign-ui3/), [Figma: approach to UI3](https://www.figma.com/blog/our-approach-to-designing-ui3/) |
| **Arc** | A command bar over tabs, history and actions. Vertical sidebar. | Unconventional chrome costs new users 1–2 weeks of friction. | [Zapier review](https://zapier.com/blog/arc-browser-review/), [Arc on Wikipedia](https://en.wikipedia.org/wiki/Arc_(web_browser)) |
| **Things 3** | Restraint: little colour, generous whitespace, careful typography, keyboard shortcuts for everything. Two Apple Design Awards. | Too sparse for data-dense work. | [Cultured Code](https://culturedcode.com/things/blog/2009/06/things-wins-apple-design-award-2009/), [Things on Wikipedia](https://en.wikipedia.org/wiki/Things_(software)) |
| **Are.na** | No likes, algorithms or ads. The interface steps back so the material is the focus. Blocks can live in many channels. | Sparse metadata. | [Pratt IxD critique](https://ixd.prattsi.org/2025/02/design-critique-are-na-ios-app/), [Are.na on Wikipedia](https://en.wikipedia.org/wiki/Are.na) |
| **Cosmos** | A calm, dark, "anti-distraction" visual library. AI auto-tags colour, mood and style. **Find similar inside clusters**. | Aesthetic-first and light on precision. | [Creative Bloq](https://www.creativebloq.com/design/social-media/what-is-cosmos-the-pinterest-alternative-for-creatives), [Kim Klassen tutorial](https://www.kimklassen.com/blog/cosmosfindsimilar) |
| **Mobbin** | **Layered filters** with **sticky tabs**. Separate search scopes (Screens, UI Elements, Flows, Text in screenshots). | Scopes add a decision before every search. | [AlternativeTo news](https://alternativeto.net/news/2025/7/new-mobbin-update-adds-layered-filters-and-sticky-tabs), [Tiny Startups review](https://www.tinystartups.com/reviews/mobbin-review) |

**Take:** generate tokens from a few inputs and gate them on WCAG contrast. Give the command palette an
`aria-activedescendant` input. Use fixed, collapsible panels. Spend colour only on the footage and the single
accent. Make search scopes optional prefixes (`in:transcript`, `in:visual`) rather than a mandatory tab.

---

## 7. Viewing environment: why the surround must be neutral

Grading suites paint walls **18% (mid) grey** so the eye holds a stable neutral reference. A coloured or bright
surround shifts perceived colour and brightness of the image
([Frame.io: building a grading suite](https://blog.frame.io/2019/07/22/building-color-grading-suite/),
[No Film School](https://nofilmschool.com/color-grading-suite-setup),
[Tuts+: neutral grey themes in Lightroom](https://photography.tutsplus.com/tutorials/want-better-color-use-neutral-gray-themes-in-adobe-photoshop-and-lightroom--cms-23342)).
ISO 3664 specifies a neutral surround of about 20% reflectance for print evaluation (summarised in the search
results above).

**Rule for Metachlorian:** the surfaces directly around footage (the grid well, player well and filmstrip)
are **exactly neutral (R = G = B)** in both themes. The accent colour never sits behind footage. It appears
only as a thin ring **outside** the media rectangle.

---

## 8. Cross-cutting patterns

### 8.1 Search
1. **One input, two grammars.** Natural language ("handheld street food close-ups, busy, night") is parsed
   into **visible, editable chips** (`shot size: close-up`, `camera movement: handheld`, `time of day: night`, plus a
   free-text residue "street food, busy"). Chips can be removed or edited. Power users can type the structured
   form directly (`fps:>=50 codec:prores`).
2. **Shot granularity by default** (F1). Toggle: *Shots* / *Files* (Resolve's Segments / Full Clips).
3. **Explain the match.** Each result carries its top two contributing signals ("close-up 0.91 · night
   0.88"). The inspector shows all of them with sources (§ signal row).
4. **Suggestions from the library's vocabulary** (Apple Photos): places, people, collections and tags that
   exist, with counts.
5. **Saved searches store the query** (iconik), so the URL is the search. Relative dates are allowed
   ("last 30 days").
6. **Visible match-strength divider** instead of silent decay (Storyblocks frustration).
7. Show search time and counts in plain text: "412 shots in 38 files · 0.4 s".

### 8.2 Large visual grids
- **Uniform 16:9 cells** with letterbox or pillarbox on a neutral well. Each cell shows its aspect ratio as
  a label. This gives: true rows and columns for arrow keys (ARIA grid), aligned timecodes, predictable
  virtualisation, and vertical footage that reads as vertical (pillarboxed) at a glance.
- **Three sizes** (S/M/L, plus `Ctrl` + `-`/`=`) and three views: **Grid** (Avid Frame), **List** (Avid
  Text) and **Log** (Avid Script).
- **Virtualise** with overscan of two rows. **Pre-allocate** scroll height from the total count. Keep the
  focused item mounted while it is scrolled out of view (React Aria Virtualizer does this; see ADR 013).
- Placeholders are **solid neutral wells at the right aspect** (no shimmer, which is motion noise). Images
  use `decoding="async"`, fixed `width`/`height` and `fetchpriority="low"` beyond the first screen.
- A **position scrubber** on the right edge (Google Photos) shows match-strength bands, or dates when sorted
  by date.

### 8.3 Video scrubbing and preview
- **Two tiers.** (1) *Scrub*: map the pointer's x position to a frame from a pre-rendered **sprite sheet**,
  addressed by a WebVTT `#xywh` map ([dev.to: ffmpeg + WebVTT sprites](https://dev.to/masonwritescode/build-scrub-bar-thumbnail-previews-with-ffmpeg-and-a-webvtt-sprite-3ei2),
  [jronallo/video_sprites](https://github.com/jronallo/video_sprites)). No decoder involved, so it is instant
  and stays at 60 fps. (2) *Play*: after a **dwell** (pointer still for 400 ms) or on **Space**, play a short
  low-bitrate preview MP4 muted in place.
- **Decoder budget.** Chromium caps WebMediaPlayers per frame (75 on desktop, 40 on mobile, since Chrome 92).
  The fix is to **pool and reuse** a few `<video>` elements
  ([Chromium media-dev](https://groups.google.com/a/chromium.org/g/media-dev/c/wEUYR7BvdZI/m/R-8X1EdiBAAJ),
  [twilio-video issue](https://github.com/twilio/twilio-video.js/issues/1528)). Metachlorian keeps a **pool of
  4** preview elements and moves them between cards.
- **Start time.** `-movflags +faststart` puts the moov atom first and removes 1–3 s of metadata fetch on slow
  links. `preload="metadata"` for players that are waiting
  ([ffmpeg-cookbook](https://ffmpeg-cookbook.com/en/articles/ffmpeg-faststart-web-playback/),
  [changethisfile](https://changethisfile.com/blog/web-video-embedding)). Short GOP proxies keep seeks cheap.
  Use `fastSeek()` while dragging and an exact `currentTime` on release
  ([video.js commit](https://github.com/videojs/video.js/commit/8c66c58)). Use `requestVideoFrameCallback` to
  update timecode readouts frame-accurately ([web.dev](https://web.dev/articles/requestvideoframecallback-rvfc),
  [MDN](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback)).
- **Intentional scrubbing** (Premiere frustration): scrubbing starts only after the pointer has *moved* at
  least 4 px inside the thumbnail. Leaving the card restores the poster frame. Hover never touches the main
  player. *Settings → Playback → Scrub on hover* turns it off.

### 8.4 Timelines and filmstrips
- One horizontal strip per asset. **Shot boundaries** are hairlines. **Matched shots** are filled bars above
  the strip (FCP keyword bars). **Selected ranges** use the accent ring. **Rights restrictions** are hatched
  ranges below the strip.
- Zoom: `Ctrl` + scroll, or `+`/`-`. Fit: `Shift+Z` (FCP convention). Never zoom on a plain scroll (Premiere
  frustration).
- Every drag on the strip (range select, trim) has a non-drag alternative: `I`/`O` at the playhead and the
  arrow keys (WCAG 2.5.7).

### 8.5 Filtering and facets
- Desktop applies filters instantly. Tablet uses a drawer with **Show N shots** to batch changes
  ([NN/g mobile facets](https://www.nngroup.com/articles/mobile-faceted-search/),
  [Algolia](https://www.algolia.com/blog/ux/faceted-search-an-overview)).
- **Applied filters show as chips** above results, each removable, with **Clear all**
  ([UXmatters](https://www.uxmatters.com/mt/archives/2009/09/best-practices-for-designing-faceted-search-filters.php)).
- Facet order runs general to specific: *Edit stage → Rights → Shot (shot size, movement) → Time and place →
  Technical*. Every value shows a live count. Zero-count values are dimmed but stay visible, so gaps are
  findable (they feed Library overview).
- Exclusion with `Alt`+click (chip becomes "not night"). Ranges (fps, duration, resolution) use a
  two-thumb slider **plus** numeric inputs (2.5.7).

### 8.6 Making density feel calm
- Neutral surfaces, **one accent**, and status colours used only with an icon and text.
- Hierarchy through **type** (weight, width, size, monospace for data) rather than boxes and borders.
  Hairline dividers, not cards inside cards.
- Quiet by default, rich on demand: cards show thumbnail, timecode, duration and at most two badges. The
  inspector holds everything else.
- No skeleton shimmer, no spinners under 400 ms, no confetti. Motion is used only for continuity (§ motion rules).

---

## 9. Accessibility for media-heavy apps (WCAG 2.2 AA)

### 9.1 Success criteria that bite hardest here

| SC (level) | What it requires | Design response |
|---|---|---|
| 1.1.1 Non-text content (A) | Text alternatives. | Each shot card's accessible name is its description plus timecode ("Close-up, hands at street food stall, night. 00:14:03:12, 6 seconds."). Decorative sprite frames are `alt=""`. |
| 1.2.2 Captions, prerecorded (A) | Captions for synchronised media. | Previews and the player offer **transcript-derived captions** (WebVTT from ingest). The `C` key or the CC button toggles them. Shown by default when the system caption preference is on. |
| 1.3.1 Info and relationships (A) | Structure in markup. | The results grid is an ARIA `grid` (React Aria GridList). Facet groups are `group`s with headings. Admin tables are real `<table>`s. |
| 1.4.3 Contrast, minimum (AA) | 4.5:1 text, 3:1 large text. | Every text token passes ≥ 4.5:1 on every surface it may sit on (system.md §1.1). Overlays on footage sit on a 72% black scrim (worst case 9.3:1 for white text). |
| 1.4.11 Non-text contrast (AA) | 3:1 for UI components and states. | Control borders ≥ 3:1. Selection and focus rings sit **outside** the footage, on known surfaces. |
| 1.4.13 Content on hover or focus (AA) | Dismissible, hoverable, persistent. | Hover previews and tooltips dismiss with `Esc`, stay while the pointer is over them, and never cover the focused card's timecode. ([W3C Understanding 1.4.13](https://www.w3.org/WAI/WCAG21/Understanding/content-on-hover-or-focus.html)) |
| 2.1.1 Keyboard (A) / 2.1.2 No keyboard trap (A) | All functionality from the keyboard. | Every surface has a keyboard map (system.md §5). The player releases focus with `Esc` or `Tab`. |
| **2.1.4 Character key shortcuts (A)** | Single-key shortcuts can be turned off, remapped, **or are active only on focus**. | J/K/L, I/O, S, B and similar work **only when the grid, player or timeline has focus**. *Settings → Keyboard* can remap or disable all single-key shortcuts ([W3C](https://www.w3.org/WAI/WCAG21/Understanding/character-key-shortcuts.html)). |
| 2.2.2 Pause, stop, hide (A) | Auto-playing motion over 5 s can be paused. | No autoplay. Dwell previews loop only while hovered. `Space` or `K` stops them. Reduced motion disables dwell-to-play. |
| 2.3.3 Animation from interactions (AAA, adopted) | Non-essential motion can be disabled. | `prefers-reduced-motion` and an in-app setting set all non-essential durations to 0 ([Silktide](https://silktide.com/accessibility-guide/the-wcag-standard/2-3/seizures-and-physical-reactions/2-3-3-animation-from-interactions/)). |
| 2.4.3 Focus order (A) | Logical order. | Search → applied chips → filter rail → results → inspector. `F6` cycles regions. |
| 2.4.7 Focus visible (AA) / **2.4.11 Focus not obscured, minimum (AA)** | Visible focus, not fully hidden by author content. | Sticky headers and toasts reserve `scroll-padding` so the focused card is never covered ([AllAccessible](https://www.allaccessible.org/blog/wcag-2411-focus-not-obscured-minimum-implementation-guide)). |
| 2.4.13 Focus appearance (AAA, adopted) | ≥ 2 CSS px perimeter, ≥ 3:1 change. | 2 px ring at 2 px offset in `--focus-ring` (≥ 11:1 against every surface) ([halfaccessible summary](https://playground.halfaccessible.com/wcag-details/2-4-13-focus-appearance)). |
| **2.5.7 Dragging movements (AA)** | Single-pointer alternative to any drag. | Drag to collection → `B` / "Add to…" menu. Timeline range drag → `I`/`O` or click-then-shift-click. Panel resize → keyboard-operable splitter with buttons. Range sliders → numeric inputs ([W3C](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html)). |
| **2.5.8 Target size, minimum (AA)** | ≥ 24×24 CSS px, or spacing exception. | Smallest interactive target is 24×24. Icon buttons on cards are 24×24 with ≥ 4 px separation. Coarse pointers (tablet) get 44 px ([wcag22aa.org](https://wcag22aa.org/new-criteria/target-size/)). |
| 3.2.6 Consistent help (A) | Help in a consistent place. | `?` (keyboard map) and Help sit at the same spot in the top bar on every surface. |
| 3.3.7 Redundant entry (A) | Don't make people re-type. | Corrections remember recent tags. Rights forms prefill from the asset or collection. |
| 4.1.2 Name, role, value (A) / 4.1.3 Status messages (AA) | Programmatic state, announced status. | Result counts, "Added to Selects", ingest progress and correction saves are announced via `role="status"` live regions, throttled to one message per second. |

### 9.2 Keyboard-first editor workflows
- **J/K/L** shuttle (repeat to go faster: 1×, 2×, 4×, 8×). `K`+`J` / `K`+`L` step frame by frame (Avid/Premiere
  convention). **I/O** set in/out. `Shift+I`/`Shift+O` go to in/out. `Alt+X` clears both. **Space**
  plays or stops, and in grids previews the focused shot.
- **Arrow navigation in grids** uses one tab stop for the grid. Arrows move between cells. `Home`/`End` go to
  the row ends, `Ctrl+Home`/`Ctrl+End` to the first/last result, `PageUp`/`PageDown` by a screen. Selection
  uses `Shift+Arrow`/`Shift+Click` for ranges and `Ctrl/Cmd+Click` or `X` to toggle.
- **Roving tabindex vs `aria-activedescendant`.** The APG grid pattern prescribes a roving tabindex (exactly
  one cell has `tabindex="0"`). For **virtualised** grids, `aria-rowcount`/`aria-colcount` on the grid and
  `aria-rowindex`/`aria-colindex` on rendered rows and cells give position, and the focused row must stay in
  the DOM while scrolled away
  ([accessibility.build grid guide](https://accessibility.build/guides/accessible-data-grid),
  [React Aria Virtualizer](https://react-aria.adobe.com/Virtualizer)). Command palettes and comboboxes use
  `aria-activedescendant` so focus never leaves the input.
- **Respecting assistive tech:** single-key shortcuts are scoped (2.1.4). Typeahead in the grid jumps to the
  next description starting with the typed letters only when shortcuts are disabled.

### 9.3 Reduced motion and media
- `prefers-reduced-motion: reduce` disables dwell autoplay, panel slides, shared-element transitions and
  smooth scroll-into-view. Pointer-driven **scrubbing stays**, because it is direct manipulation, not
  animation. Toasts appear without movement.
- Autoplay is never used. All previews are muted. Audio plays only in the player, on request.

---

## 10. Frustration index (what we refuse to ship)

| Frustration | Seen in | Metachlorian rule |
|---|---|---|
| Waiting for thumbnails | Premiere | A file is searchable only once poster, sprite and preview exist (Ingest shows the state). |
| Accidental scrubbing, hijacked viewer | Premiere, FCP | Scrub needs pointer movement inside the frame and never moves the main player. Setting to disable. |
| Relevance silently decays | Storyblocks, Pond5 | Visible "Weaker matches below" divider with a threshold control. |
| Missing technical facets | Storyblocks | Codec, bit depth, log, alpha, HDR and edit stage are facets. |
| Status buried in a panel | Frame.io V4 | Rights and role on the card. |
| Unexplained AI results | Apple Photos | "Why it matched" on hover and in the inspector. |
| Clunky, form-heavy search | iconik, CatDV | One input. Chips appear as you type. Structured syntax is optional. |
| Floating or novel chrome | Figma UI3 beta, Arc | Fixed, resizable, collapsible three-pane layout. |
| Corrections that don't stick | (generic AI tagging) | Human corrections are a distinct signal source that outranks the model, is shown with a marker, and survives re-analysis (system.md signal row). |

---

## 11. Principles carried into the directions

1. **Footage is the only colour.** Surfaces are neutral, and there is one accent that rarely occurs in footage.
2. **The shot is the unit.** Timecode in/out is visible wherever a shot is.
3. **Evidence over magic.** Every match explains itself. Every signal shows source, confidence and whether a
   human confirmed or corrected it.
4. **Instant or honest.** Interactions under 100 ms feel instant. Anything slower shows real progress, never
   decorative shimmer.
5. **Editor muscle memory** (J/K/L, I/O, Space, arrows), scoped so it never fights screen readers or dictation.
6. **Governance is visible.** Rights and "leaves this machine" are on the surface where the decision is made.
7. **Familiar geometry, novel substance.** Three-pane NLE layout. The innovation lives in search, evidence
   and handoff.
