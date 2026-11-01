# Changelog

Notable changes per release. Full commit history, desktop installers and Docker
image tags are on the [releases page](https://github.com/JeremySNR/Metachlorian/releases).

This project uses [semantic versioning](https://semver.org/), loosely: while
still pre-1.0, minor bumps carry new features and patch bumps carry fixes.

## [Unreleased]

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
