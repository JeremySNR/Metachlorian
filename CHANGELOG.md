# Changelog

Notable changes per release. Full commit history, desktop installers and Docker
image tags are on the [releases page](https://github.com/JeremySNR/Metachlorian/releases).

This project uses [semantic versioning](https://semver.org/), loosely: while
still pre-1.0, minor bumps carry new features and patch bumps carry fixes.

## [Unreleased]

### Added

- **The desktop app installs everything it needs.** The Windows installer, the macOS disk image and the Linux AppImage now include their own Python, the Metachlorian engine, FFmpeg and the web app, so nothing else has to be installed first.
- The first time it opens, the desktop app downloads the analysis models (about 1.7 GB, once) and shows its progress. If the download fails it says so and offers **Try again**, keeping anything already downloaded.

### Fixed

- Semantic search and zero-shot labels now work on Apple Silicon Macs. Embedding shots failed when analysis used Apple's Core ML accelerator; it now runs on the CPU unless `METACHLORIAN_COREML=1` is set.

- The macOS desktop download no longer opens with "Metachlorian is damaged and can't be opened". The app is now ad-hoc signed, so macOS shows its usual unidentified-developer prompt and **System Settings → Privacy & Security → Open Anyway** works. It is still not signed with an Apple Developer ID or notarised.
