# Changelog

Notable changes per release. Full commit history, desktop installers and Docker
image tags are on the [releases page](https://github.com/JeremySNR/Metachlorian/releases).

This project uses [semantic versioning](https://semver.org/), loosely: while
still pre-1.0, minor bumps carry new features and patch bumps carry fixes.

## [0.3.0] - 2026-11-01

Photos and the Lightroom Classic editing preview are now included in the desktop installers. Open **Photos → Enable Photos** to get started.

### Added

- Index photo folders or a Lightroom Classic catalogue in place. Search photographs and named people, compare related frames, and give Codex or another MCP agent the previews and metadata it needs to choose your favourites.
- Create recoverable edits on Lightroom virtual copies, review fresh renders, and save reviewed selections to a named collection. Snapshots and revision checks help recover interrupted edits and detect intervening changes.
- Desktop installers include local RAW/HEIC decoders and the Lightroom connector. Photo models are available from Library details and reuse downloads already installed for video analysis.

### Improved

- Guided photo setup walks through choosing a source, connecting Lightroom and configuring your agent. **Check connection** shows the responding Lightroom version, catalogue and editing availability.
- Photos opens to the gallery, with separate Library, Edits and Activity views, adjustable thumbnails and a persistent selection bar. Setup and analysis/storage details open when needed.
- **Create edit brief** copies selected photo references and your requested look to your agent, with Natural, Warm film and Black & white starting points. These are briefs, not automatic presets.
- The photo inspector scrolls independently, keeps previous/next navigation accessible, and explains actual exposure, focus, framing and model coverage in Overview, Analysis, People and Metadata views.
- Edits shows a source photograph alongside its rendered virtual copy. Photo search shortcuts stay within Photos.

### Fixed

- Concurrent playlist downloads now share their source folder reliably, avoiding intermittent import failures when two videos finish together.
- Folder-indexed files match existing Lightroom masters by path for current settings and previews, including RAWs without a local decoder. Already-indexed originals do not need to be copied or re-indexed.
- Connection and preview failures explain the next step. Copied connector files are no longer treated as proof of a working Lightroom connection, and the plug-in shows its last authenticated request.
- The setup guide keeps its current step when the first photos arrive.

### Upgrading

- Install the new desktop version. If you already added the Lightroom plug-in, open **Photos → Setup & agent**, copy the connector files again, then use **Reload Plug-in** in Lightroom and **Check connection** in Metachlorian.
- Originals stay in place. Existing libraries and shared model downloads are reused; previews have a default 256 MiB cache budget. Lightroom's own catalogue and previews use separate storage.

### Validation and preview limits

- The desktop package checks run on Windows, macOS (Apple Silicon) and Linux. Automated checks cover the photo service, Lua SDK doubles, TCP transport, REST/MCP, browser workflows and a synthetic 100,000-photo storage/retrieval benchmark.
- Lightroom global controls target Classic **14.2–15.6**, checked per photograph; AI subject/sky/background masks require **15.6**. Live Lightroom certification on macOS and Windows and real-photo preference evaluation remain pending. Linux can index folders; Classic editing needs macOS or Windows on the same computer and OS account.
- Photo analysis supplies retrieval and qualified preview measurements. The connected vision-capable agent judges the photograph and the edit; indexing does not generate a full photographic critique or guarantee a better image.
- Windows builds remain unsigned; macOS builds are ad-hoc signed and not notarised. See the [setup guide](https://github.com/JeremySNR/Metachlorian/blob/main/docs/photos.md) for connection, storage and editing limits.

## [0.2.0] - 2026-11-01

### Added

- Library readiness shows searchable files, previews, missing index entries, failed or unavailable analysis, and unknown recording dates.
- AI agents can create and refine saved selections with notes, trims and shot order through MCP, subject to their permissions and footage rights.
- Camera metadata records named Log profiles and colour gamut, retaining evidence and distinguishing confirmed metadata from visual estimates.
- Footage can be searched using evidence-based place recognition and camera continuity, with optional GPU acceleration and configurable analysis lanes.

### Improved

- Recursive folder imports show persistent scan progress, duplicate counts and errors; excluded folders stay excluded from future scans.
- Files browsing includes unfinished videos, pages through the full library, and supports recording-date sorting with working thumbnail sizes and Grid, List and Log views.
- MCP reports incomplete analysis, exposes chronological browsing and complete pagination, and explains how to inspect footage before selecting or exporting it.
- Library data, models and previews can be kept on a separate drive while originals in watched folders are read in place.

### Fixed

- Interrupted or failed indexing is recorded and retried locally without repeating completed AI analysis.
- Camera and Exif recording dates sort and filter consistently; folder dates no longer substitute file modification dates for missing recording metadata.
- Codex-backed analysis recovers after desktop updates move its executable.
- Collection edits reject invalid trims and orders, cannot change another collection's entries, and roll back failed batch additions.
- Export packages retry temporary Windows file locks and preserve existing output folders.
- Analysis avoids unextractable final-frame segments, preserves caption evidence and shot loudness, and keeps runnable jobs moving through resource backlogs.

## [0.1.0] - 2026-10-13

First release. Metachlorian watches your footage once, on your own computer, and builds a shot-by-shot index that you and AI agents can search: by what's in a shot, what's said, how it was filmed and whether you're cleared to use it. Download the desktop app below for Windows, macOS (Apple Silicon) or Linux, or run the server with Docker (`ghcr.io/jeremysnr/metachlorian:0.1.0`).

### Added

- **The desktop app installs everything it needs.** The Windows installer, the macOS disk image and the Linux AppImage now include their own Python, the Metachlorian engine, FFmpeg and the web app, so nothing else has to be installed first.
- The first time it opens, the desktop app downloads the analysis models (about 1.7 GB, once) and shows its progress. If the download fails it says so and offers **Try again**, keeping anything already downloaded.

### Fixed

- Metachlorian now runs on Windows. It previously stopped at start-up there, because it used a file lock that only exists on macOS and Linux.
- Semantic search and zero-shot labels now work on Apple Silicon Macs. Embedding shots failed when analysis used Apple's Core ML accelerator; it now runs on the CPU unless `METACHLORIAN_COREML=1` is set.
- The macOS desktop download no longer opens with "Metachlorian is damaged and can't be opened". The app is now ad-hoc signed, so macOS shows its usual unidentified-developer prompt and **System Settings → Privacy & Security → Open Anyway** works. It is still not signed with an Apple Developer ID or notarised.
