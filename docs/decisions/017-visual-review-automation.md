# 017. Visual review automation: screenshots and journey videos

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
Maintainers and reviewers, human or agent, need **screenshots and video recordings of end-to-end journeys** on every change, stored under `review/`. Examples:
- first run and choosing solo or team mode;
- add a watch folder, then watch ingest progress;
- search, filter chips, open a shot, scrub the proxy;
- build a collection, then drag out or copy the path;
- admin job queue.

The UI ships two ways (001), so automation must drive:
- **(a) the web build**, served by the core, at desktop and tablet viewports;
- **(b) the Electron app**, for shell-only features such as drag-out, local-core start and mDNS browsing.

Build environment:
- Chromium is preinstalled for Playwright under `/opt/pw-browsers` (`chromium-1194`, `chromium_headless_shell-1194`, `ffmpeg-1011`), and a global `playwright@1.56.1` matches it.
- `xvfb-run` and system `ffmpeg` are present.
- No GPU, 4 CPUs, 15 GB RAM.
- npm, PyPI, GitHub releases and Docker Hub are reachable. Hugging Face is blocked, which is irrelevant here.

Cutawan already uses this pattern: Electron under `xvfb-run … --no-sandbox --disable-gpu` with a `CUTAWAN_SMOKE` auto-screenshot walk.

## Options considered
| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **Playwright** (`@playwright/test`) | Chromium, Firefox and WebKit from one API. Device emulation (iPad viewports). `toHaveScreenshot` visual diffs, with lossless WebP goldens since 1.62. Traces. Per-context `recordVideo` (WebM). Since **1.59**, a `page.screencast` API with start/stop, action highlighting, chapter titles and overlays aimed at "video evidence" ([v1.59.0 notes](https://github.com/microsoft/playwright/releases/tag/v1.59.0)). **Experimental Electron driver** `_electron.launch()` with `firstWindow()` and `recordVideo` ([API](https://playwright.dev/docs/api/class-electron)). | Apache-2.0 | Headless Chromium on CPU. Video via the bundled ffmpeg. | Fast, parallel workers | Very mature. v1.63.0 latest; bundles Chromium 153 ([releases](https://github.com/microsoft/playwright/releases)). | 97k★, Microsoft-backed, monthly releases ([repo](https://github.com/microsoft/playwright)) |
| Puppeteer | Chrome and Firefox (CDP / WebDriver BiDi). `page.screencast()` needs ffmpeg ([docs](https://github.com/puppeteer/puppeteer/blob/main/docs/api/puppeteer.page.screencast.md)). No test runner or visual-diff built in. Electron only by attaching over `--remote-debugging-port`. | Apache-2.0 | Same | Fast | Mature | 95.6k★, Google Chrome team ([repo](https://github.com/puppeteer/puppeteer)) |
| Cypress | Great interactive runner. Video recording in `cypress run` for Chrome-family browsers. **Cannot drive an Electron app's own windows.** Its bundled Electron *test browser* is deprecated ([launching browsers](https://docs.cypress.io/app/references/launching-browsers)). No WebKit video. | MIT (Cloud is commercial) | Heavier (own Electron) | Slower, serial per spec | Mature | 51k★ ([repo](https://github.com/cypress-io/cypress)) |
| WebdriverIO + `@wdio/electron-service` | Real Electron testing through Chromedriver, API mocking, automatic Xvfb ([service](https://github.com/webdriverio-community/wdio-electron-service)). Video only via third-party reporters that stitch screenshots. | MIT | Needs a Chromedriver matching the Electron version | Slower (WebDriver round-trips) | Mature | 9.8k★. The Electron service moved into the official org ([repo](https://github.com/webdriverio/webdriverio)). |

## Evidence
- Only Playwright covers **both** targets with one API and one runner: the web at desktop and iPad sizes, and Electron via `_electron`, including real video. Cypress cannot drive Electron windows at all. WebdriverIO can, but has no native video. Puppeteer needs custom glue for everything beyond capture.
- Known Playwright + Electron caveats:
  - `recordVideo` at launch can leave the first `BrowserWindow` on a blank URL ([pi-gui#111](https://github.com/minghinmatthewlam/pi-gui/pull/111)).
  - `recordVideo` can time out on Windows ([playwright#26648](https://github.com/microsoft/playwright/issues/26648)).
  - Launching a packaged `.exe` has quirks ([#28669](https://github.com/microsoft/playwright/issues/28669)).

  So Electron journeys should prefer screenshots and traces, and record video on the web build. Simon Willison documents the same pattern running in CI ([TIL](https://til.simonwillison.net/electron/testing-electron-playwright)).
- **Version pinning matters here.** The preinstalled browsers are revision 1194 for Playwright 1.56.1. A newer `@playwright/test` (1.59+ for `page.screencast`) expects a different Chromium revision and would try to download it from Playwright's CDN, which this environment may not reach. `recordVideo` and screenshots are available in 1.56.

## Decision
Adopt **Playwright** (`@playwright/test`, TypeScript) in `review/`, with two projects:
1. **`web`**: starts the core with a seeded fixture library (tiny synthetic clips generated by ffmpeg, no network) and serves the built UI.
   - Viewports: 1440×900 desktop, plus iPad (1024×768 landscape / 768×1024 portrait) via device emulation.
   - Each journey writes named screenshots plus a WebM through `recordVideo` (`video: 'on'`) and a trace (`trace: 'retain-on-failure'`).
   - Visual diffs (`toHaveScreenshot`) on a small set of stable views, with animations off and fixed fonts and seeds.
2. **`electron`**: `_electron.launch({ args: [main, '--no-sandbox', '--disable-gpu'] })` under `xvfb-run -a --server-args="-screen 0 1600x1000x24"`, the same as Cutawan.
   - Covers first run, starting the local core, team-mode connection to a mock core, and the drag-out IPC call. A real OS drop target cannot be automated headlessly, so the test asserts that `webContents.startDrag` was invoked with the right path.
   - Screenshots and traces are the default. Video is opt-in, because of the known `recordVideo` issues.

Version policy: **pin `@playwright/test` to `1.56.1`** to match the preinstalled `/opt/pw-browsers` Chromium (set `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`). Upgrade to ≥ 1.59 for `page.screencast` (annotated action videos) only when the matching browser revision is available in CI. Concatenate or transcode the WebM files with system `ffmpeg` into one MP4 per journey for reviewers. Outputs go to `review/out/<journey>/` with a JSON manifest (step, screenshot, timestamp, viewport) that agents can read.

## Consequences
- One tool, one language (TS, the same as the UI), and the same patterns as Cutawan's smoke test. Reviewers get images, videos and traces.
- `_electron` is officially "experimental", so API changes are possible. Keep Electron journeys thin, and push UI logic coverage to the web project.
- Videos are CPU-encoded WebM. On 4 CPUs, run journeys with `workers: 2` to avoid dropped frames.
- Pinning to 1.56.1 defers the screencast annotations. Action captions can be approximated by overlaying step titles with `ffmpeg drawtext` from the manifest.
- Real drag-and-drop into an NLE remains a manual check on release candidates.

## Revisit when
- Playwright's Electron support leaves "experimental", or breaks on a new Electron major.
- CI can fetch matching browser revisions, which unlocks `page.screencast` (1.59+) with annotated actions.
- The desktop shell changes (001). For example, Tauri 3 + CEF would need a WebDriver or CDP-attach approach instead.
- Visual-diff flakiness exceeds ~2% of runs. Move diffs to a containerised, font-pinned renderer.
