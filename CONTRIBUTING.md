# Contributing

## Release notes

Every change people will notice needs a line in `CHANGELOG.md` under
`## [Unreleased]`, grouped as `### Added`, `### Improved` or `### Fixed`. CI
fails a pull request that changes the core (`core/metachlorian/`), the web app
(`app/src/`), the desktop shell (`desktop/src/`), the Docker image or their
dependencies without one. For internal-only changes (tests, CI, docs,
refactors with no visible effect), add the `no release notes` label instead.

These lines are what people read: the release workflow publishes a version's
section as its GitHub release notes. So write them for someone using
Metachlorian, not for a code reviewer:

- Say what changed for them: "Search finds shots by what people say in them"
  rather than "Add transcript FTS to the hybrid ranker".
- One change per bullet, plain words, no file or function names.
- Measurements, failed trials and limits go in a `### Validation` section (or
  a doc linked from it).

## Releasing

The core, web app, desktop app and Docker image share one version, kept in
step by `scripts/version.mjs` (CI fails if they drift).

1. Run `node scripts/version.mjs 0.2.0`. It sets the version in
   `core/pyproject.toml`, `core/metachlorian/__init__.py`, `app/` and
   `desktop/`, and renames `## [Unreleased]` to `## [0.2.0] - <today>`.
2. Commit those changes with a message starting `Release v0.2.0` and land it on
   the default branch (or push a `v0.2.0` tag instead).

The [release workflow](.github/workflows/release.yml) then:

- refuses to build a version with no notes, or a tag that doesn't match the
  version;
- builds the macOS (Apple Silicon), Windows and Linux installers;
- uploads them to a draft release, checks every installer against its update
  manifest (`latest*.yml`) by size and checksum, locally and on GitHub, and
  only then publishes the release as Latest with the changelog section as its
  notes;
- pushes the Docker image as `ghcr.io/jeremysnr/metachlorian:<version>`,
  `:v<version>` and `:latest`.

A version that is already published can't be released again; bump it. If a
run fails partway, re-run it: the draft is reused and assets are replaced.

Model weights are published separately, by hand, with the **Publish models**
workflow (`.github/workflows/models.yml`).
