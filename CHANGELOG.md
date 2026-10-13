# Changelog

Notable changes per release. Full commit history, desktop installers and Docker
image tags are on the [releases page](https://github.com/JeremySNR/Metachlorian/releases).

This project uses [semantic versioning](https://semver.org/), loosely: while
still pre-1.0, minor bumps carry new features and patch bumps carry fixes.

## [Unreleased]

### Fixed

- The macOS desktop download no longer opens with "Metachlorian is damaged and can't be opened". The app is now ad-hoc signed, so macOS shows its usual unidentified-developer prompt and **System Settings → Privacy & Security → Open Anyway** works. It is still not signed with an Apple Developer ID or notarised.
