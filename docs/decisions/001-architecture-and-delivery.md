# 001. Architecture and delivery: headless core, one UI shipped as web app and Electron shell

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
Metachlorian indexes every shot in a footage library and makes it searchable by people (UI) and AI agents (MCP). The proposal is a **headless core service** (ingest, analysis, search, REST API, MCP) plus a **desktop-first client**. The client runs in two modes: **solo** (the app starts a local core) and **team** (the app connects to a shared core on a server or NAS). The spec requires the UI to be responsive down to tablet.

Constraints:
- Apache-2.0 and self-hostable.
- Python is the natural language for the analysis stack (ONNX Runtime, PyTorch, ffmpeg bindings, embeddings).
- The same author ships Cutawan, an Electron + Vite + React 19 + Tailwind 4 + TypeScript desktop app. It uses Electron 35, electron-builder 25 and electron-updater, and has an Xvfb screenshot smoke test.
- Build environment: no GPU, 4 CPUs, 15 GB RAM. Hugging Face is blocked; PyPI, npm, GitHub releases and Docker Hub are reachable.

### Who needs what
| User | Where they work | What they need from the client | Best fit |
|---|---|---|---|
| Editor | NLE workstation (Premiere, Resolve, Avid, FCP) | Drag **real files** from the shot list onto a timeline. Open the original from the shared storage path. Smooth scrubbing. Works offline in solo mode. | **Desktop** (only a native shell can start an OS file drag) |
| Content / marketing lead | Laptop or tablet, browser, often remote | Search, review, collect and share selects. No install. iPad-size layouts. | **Web** (tablets cannot run Electron, Tauri or Wails) |
| AI agent | MCP client (Claude Desktop/Code, IDEs, servers) | A stable MCP tool schema with structured filters. Streamable HTTP for remote cores, stdio for local. | **Core only**, no UI |
| Admin | Server/NAS console, browser | Install, watch folders, job queue, users, upgrades. Usually on a headless box. | **Web UI served by the core** plus a container/service |

Two of the four users need a web client, and the tablet requirement alone rules out a desktop-only UI. The editor needs a native shell for drag-out. So the answer is **both, from one UI codebase**.

## Options considered
### A. Client delivery
| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| Desktop-only app | Best editor experience. Fails the tablet requirement and remote leads. | n/a | Per-seat install | n/a | n/a | n/a |
| Web-only (served by core) | Meets tablet and remote needs. No real-file drag-out: Chrome's non-standard `DownloadURL` drag only downloads a copy, and only in Chrome ([web.dev](https://web.dev/case-studies/box-dnd-download), [dt.in.th](https://dt.in.th/DownloadURL)). No local "solo" core without a separate install. | n/a | Any browser | n/a | n/a | n/a |
| **One React UI served by the core as a web app and wrapped in a desktop shell** | Meets every user above. Shell-only features (drag-out, start a local core, reveal in Finder, mDNS browse) sit behind a small capability bridge. | n/a | Browser or desktop | n/a | Pattern used by Jellyfin (server-hosted web client plus desktop wrappers, [docs](https://jellyfin.org/docs/general/post-install/networking/)) and Immich (server serves web UI and API) | n/a |

### B. Desktop shell
| Option | Quality (video, drag-out) | Licence | Footprint* | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **Electron** | Bundled Chromium is the same on all OSes. H.264/AAC are built in through `proprietary_codecs` ([electron#633](https://github.com/electron/electron/issues/633), [vscode#156558](https://github.com/microsoft/vscode/issues/156558)). HEVC hardware decode since Electron 22 on macOS, Windows and Linux (VAAPI only) ([StaZhu guide](https://github.com/StaZhu/enable-chromium-hevc-hardware-decoding)). `webContents.startDrag` drags real local files out to Finder or an NLE, but only one file at a time on Windows ([tutorial](https://github.com/electron/electron/blob/main/docs/tutorial/native-file-drag-drop.md), [fileside notes](https://www.fileside.app/blog/2019-04-22_fixing-drag-and-drop/)). | MIT | 481 MiB RSS at idle. 471 MiB bundle expanded. | Fastest incremental rebuild (0.68 s) | Very high. 44.5.1 stable on 2026-09-30, 45 in alpha with Chromium 156 ([releases](https://github.com/electron/electron/releases)). | Very active. Supports the latest 3 majors; **Electron 35 (Cutawan) reached end of life on 2025-09-02** ([endoflife.date](https://endoflife.date/electron)). |
| Tauri 2 (wry) | System webview: WKWebView, WebView2, WebKitGTK. On Linux, WebKitGTK plays media through GStreamer, so codecs depend on the distro's plugins. GStreamer rejects custom URI schemes, so media must be served over http(s) ([tauri-video-plugin linux notes](https://github.com/get-air/tauri-video-plugin/blob/main/docs/linux.md)). AppImage needs `bundleMediaFramework` to ship GStreamer. WebView2 needs the Store "HEVC Video Extensions" for HEVC ([photo-manager#869](https://github.com/jackal998/photo-manager/issues/869)). Drag-out through the community `tauri-plugin-drag` (MIT/Apache, 120★) ([drag-rs](https://github.com/crabnebula-dev/drag-rs)). | MIT/Apache-2.0 | 353 MiB RSS. ~20 MiB executable. | Slow Rust incremental rebuild (6.3 s) | High (2.x stable) | Active. **v3 is in alpha and adds an optional CEF (Chromium) runtime** ([tauri-runtime-cef v3.0.0-alpha.1](https://github.com/tauri-apps/tauri/releases/tag/tauri-runtime-cef-v3.0.0-alpha.1)). That signals webview inconsistency is a known pain. |
| Tauri 3 + CEF | Chromium everywhere, so video behaves like Electron | MIT/Apache-2.0 | 751 MiB RSS, 342 MiB bundle | as Tauri | **Alpha** (alpha.4/5, 2026-10-01) | Active |
| Wails (Go) | System webview, so it has the same Linux/GStreamer and Windows HEVC caveats as Tauri | MIT | 270 MiB RSS, 16 MiB executable | 2.6 s rebuild | v2 stable; v3 still beta (v3.0.0-beta.27) ([releases](https://github.com/wailsapp/wails/releases)) | Active |
| Electrobun (Bun + Zig) | System webview by default, with an optional `bundleCEF`. BSDIFF delta updates. | MIT | 384 MiB RSS, 71 MiB installed | fast | v1 recently. Official on macOS 14+, Win 11, Ubuntu 24.04; other Linux distros are community-supported ([repo](https://github.com/blackboardsh/electrobun)). | 12.9k★. The author limits outside contributions. |
| Neutralinojs | System webview through webview/webview. Native APIs are minimal. | MIT | small | fast | Mature but niche ([repo](https://github.com/neutralinojs/neutralinojs)) | 8.7k★ |

\*The RSS and bundle numbers come from one same-app comparison on macOS arm64, dated 2026-10 ([pierophp/ai-mission-manager#135](https://github.com/pierophp/ai-mission-manager/issues/135)). Vendor marketing claims bigger gaps ([rustify.rs](https://rustify.rs/articles/rust-tauri-vs-electron-2026)), and Tauri's own tracker has questioned how memory is measured ([tauri#5889](https://github.com/tauri-apps/tauri/issues/5889)).

### C. Running the core
| Option | Notes |
|---|---|
| PyInstaller sidecar | Ships CPython plus .pyc files, and almost every library works unchanged. Cold start is 1-3 s in onefile mode, so prefer onedir. GPL with a bootloader exception, which lets us ship it in Apache-2.0 apps ([comparison](https://blog.thoughtparameters.com/post/nuitka_vs_pyinstaller_python_packaging/)). |
| Nuitka | Compiles Python to C. Builds are slower and ML wheels sometimes need hand fixes. Apache-2.0. |
| **python-build-standalone + locked venv (via uv)** | A relocatable CPython (MPL-2.0) maintained by Astral, now being acquired by OpenAI ([repo](https://github.com/astral-sh/python-build-standalone), [The Register](https://www.theregister.com/2026/03/19/openai_aims_for_the_stars/)). Nothing is frozen, so wheels such as onnxruntime and torch load normally. The first-run "install components" step can be shared with Cutawan's local-whisper wizard. |
| **Container (OCI image)** | The natural fit for team mode on a NAS or server (Synology Container Manager, Unraid, compose). Use `network_mode: host` if the core must advertise over mDNS, because multicast does not cross a Docker bridge ([evcc discussion](https://github.com/evcc-io/evcc/discussions/11294)). |
| System service | systemd, launchd or a Windows service for bare-metal team installs. The binary is the same as in solo mode. |

Discovery and connection:
- The core advertises `_metachlorian._tcp` over DNS-SD, using python-zeroconf (pure Python, LGPL-2.1, used as a dependency only). The app browses with `bonjour-service` (MIT, TypeScript) ([npm](https://www.npmjs.com/package/bonjour-service)).
- Manual URL entry and a config file are the fallback, for VLANs, VPNs and Docker bridges.
- Every client probes `GET /api/health` (version, API level, mode, auth required) before connecting, and refuses a core whose API level is incompatible.
- MCP is exposed as Streamable HTTP at `/mcp` on the same FastAPI app. The official SDK supports mounting it, but there are known pitfalls with `BaseHTTPMiddleware` and mounting ([python-sdk#1367](https://github.com/modelcontextprotocol/python-sdk/issues/1367), [#2702](https://github.com/modelcontextprotocol/python-sdk/issues/2702)). A stdio shim covers local MCP clients.

### D. Repository layout
| Option | Notes |
|---|---|
| **Own repo, internal monorepo** (`core/`, `app/`, `eval/`, `review/`, already scaffolded) | One Apache-2.0 licence. Python and TS live side by side, and releases are versioned together so the UI and API match. |
| Shared monorepo with Cutawan | Cutawan is MIT, a single TS package with no backend and its own release train. Sharing would couple unrelated release cycles and mix licences in one tree. The only real overlap is the Electron shell plumbing (builder config, updater, signing, Xvfb smoke test), the ffmpeg helpers and the Tailwind setup. |

## Evidence
- Video: the UI will play **core-generated H.264 proxies** (MP4/fMP4, optionally HLS) served over HTTP. Neither Chromium nor WebView2 decodes ProRes. WebKit plays only what Apple builds in ([totalmedia.ai](https://www.totalmedia.ai/en/resources/blog/why-safari-struggles-with-video-formats)). WebView2 HEVC depends on a Store extension. WebKitGTK depends on GStreamer plugins. Proxies make the client codec-independent in every shell and in every tablet browser. Electron still has the most predictable fallback for HEVC sources.
- Drag-out to NLEs: Electron's `startDrag` works with existing local paths, which suits files on mounted NAS shares. Tauri needs a third-party plugin. A pure web client cannot do it.
- Footprint: the Python core plus ONNX models (hundreds of MB to over 1 GB) dwarfs the 100-450 MB difference between shells. The shell's footprint is not what decides this.
- Reuse: Cutawan already has a working Electron build, signing hooks (`electron-builder`, `electron-updater`) and an Xvfb screenshot walk. That is directly reusable. Note that electron-builder v26/27 moved Windows signing options to `win.sign` ([docs](https://www.electron.build/docs/features/code-signing/code-signing-win/)).

## Decision
**Confirm the tentative choice, with refinements:**
1. **Core:** Python 3.11+ with FastAPI. It serves `/api` (REST, OpenAPI), `/mcp` (Streamable HTTP) and the built UI as static files. The same artefact runs as the solo sidecar, a container and a system service.
2. **UI:** one React 19 + TypeScript + Vite + Tailwind 4 codebase, matching Cutawan's stack. It is responsive from tablet (768 px) up. Platform features go through a `capabilities` bridge (`canDragOut`, `canStartLocalCore`, `canBrowseMdns`), and the web build degrades cleanly: "copy path" and "download proxy" replace drag-out.
3. **Desktop shell: Electron** on a current supported major (44.x), not Tauri. The reasons:
   - Chromium is the same everywhere, which matters for video and for Linux in particular.
   - `startDrag` is first-party.
   - Cutawan's tooling can be reused.
   - The Playwright `_electron` path exists (see 017).

   Tauri's own move toward an optional CEF runtime confirms the webview-consistency problem. Tauri 3 + CEF is not yet stable, and its footprint is larger than Electron's.
4. **Solo mode:** ship the core as python-build-standalone plus a locked venv (uv). Heavy model packs download on first run from GitHub releases. The fallback is a PyInstaller onedir build if relocation problems show up. The shell starts the core on `127.0.0.1` with a random port and a per-launch token, and stops it on quit.
5. **Team mode:** an OCI image published to Docker Hub/GHCR is the primary route. systemd/launchd units are secondary. Discovery uses DNS-SD first, then a manual URL, then `/api/health` negotiation. HTTPS and auth are required whenever the core binds to anything other than loopback.
6. **Repo:** stay a standalone monorepo. Cutawan code can be copied under its MIT terms, keeping its copyright notice. Extract a shared package only if the duplication becomes painful.

## Consequences
- One UI serves editors, leads and admins, and tablets work through the browser. The MCP tools sit on the same API, so agents and humans see the same results.
- Electron adds ~470 MiB to the install and more idle RAM than Tauri or Wails. That is acceptable next to the core, but the app should be lean: one window, no hidden renderers.
- We must build a proxy pipeline, which is also needed for thumbnails and scrubbing.
- Electron security has to be kept up to date: majors every ~8 weeks, `contextIsolation`, sandboxed renderer, no `nodeIntegration`. Cutawan should also upgrade from the end-of-life Electron 35.
- macOS notarisation and Windows signing (Azure Trusted Signing or an HSM key) are needed for a smooth install. Cutawan currently ships unsigned.
- The API must be versioned (API level in `/api/health`) because desktop clients and a NAS core will drift apart.

## Revisit when
- Tauri 3 with the CEF runtime reaches stable and its drag-out is first-party. Then re-measure RSS and bundle against Electron.
- Electrobun's CEF mode and Linux support become official across distros.
- The web platform gains a standard for dragging out real files, which would remove the main reason for the shell.
- Users ask for a native tablet app (Capacitor would wrap the same UI).
- Bundled core size passes ~1.5 GB, or relocatable-venv problems appear on any OS. Then switch to PyInstaller or Nuitka onedir.
- Cutawan and Metachlorian start sharing more than shell plumbing. Then reconsider a shared package or workspace.
