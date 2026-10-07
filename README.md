# Metachlorian: footage search for AI video editors

**AI can edit video. It can't watch every frame of every file each time it needs a shot.** Metachlorian watches your
footage once, on your own hardware, and builds a shot-by-shot index that AI agents can search in milliseconds over MCP or
a REST API.

> "A two-second cutaway of a yellow cab, camera panning left, no faces."
> "B-roll that works under the line *we nearly missed the ferry*."
> "Slow, wide drone shots of a coastline at golden hour, no people, at least 8 seconds, 4K."
> "Wide shots of Lisbon we're cleared to use on paid social."

Every result comes back as a shot with exact in and out points, the signals that matched and how confident each one is,
and a rights verdict for the use you stated. Your agent decides the edit. Metachlorian finds the footage.

- **Built for agents.** An MCP server and REST API that work with Claude, Codex, Cursor and any MCP client. Read-only by
  default, scoped tokens for anything more, every call audited.
- **Measured, not guessed.** Shot boundaries, camera motion, pace, loudness and image quality are computed. Models are
  used for meaning: what's in the shot, what's said and when, what's written on screen, who is in it.
- **Straight to the timeline.** Hand selected shots to [Cutawan](https://github.com/JeremySNR/cutawan), or to any editor
  that reads OpenTimelineIO, FCPXML or CMX 3600 EDL.
- **Self-hosted and open source (Apache-2.0).** Runs on a CPU, faster with a GPU. Footage, frames and faces stay on your
  machine unless an admin chooses a hosted model. One exception is on by default: new YouTube imports share machine
  metadata with a public community index ([details and opt-out](#community-sharing)).
- **A web and desktop app for people too.** Search, review what the index says about each shot, and correct it.

<!-- TODO: replace with a short GIF of an agent building an edit from search results (docs/media/demo.gif). -->
![Search with parsed query chips, results and why each shot matched](review/m4/screens/01-search-results--desktop-light.jpg)

## Why not just give the model the video?

Vision models can describe footage, but asking one to watch hours of video for every editing decision is slow, expensive
and imprecise. An edit makes hundreds of small decisions. Metachlorian does the watching once, at import, so each
decision becomes a query.

| | Model watches the footage | Metachlorian |
|---|---|---|
| Each question | Re-reads hours of video | Queries an index: median 325 ms at 1.6 million shots ([eval](eval/README.md)) |
| Cost | Grows with every question | Paid once, at import |
| Precision | "Somewhere around four minutes in" | Shot boundaries and word-timed speech, down to the frame |
| Evidence | Take the model's word for it | Every signal has a value, a source, a confidence and a model version |
| Your footage | Uploaded to a provider | Analysed locally by default |

## Connect your agent (MCP)

Start the server, create a token in **Settings → Agents** (or `metachlorian token my-agent`), then add it to your MCP
client:

```json
{
  "mcpServers": {
    "metachlorian": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp/",
      "headers": { "Authorization": "Bearer mc_xxxxxx_..." }
    }
  }
}
```

On the same machine, `metachlorian mcp` runs over stdio instead (read-only without a token).

A 60-second edit of the kids on rides from a folder of holiday footage takes four calls:

1. `list_folders(query="disney")` → `Holidays/Disney 2026` (41 files, 2.3 h)
2. `search_shots(query="kids on a ride, smiling", folder="Disney 2026", filters={"min_duration": 2})`
3. `find_similar(shot_id=<best one>, folder="Disney 2026")` for more like it
4. `build_package(items=[...], name="Disney rides 60s")` → a package Cutawan or any editor can open

Tools for search, shot and file records, similar shots, rights checks, clip export, packages, folders, collections,
people and vocabularies are listed with their scopes in [docs/agents.md](docs/agents.md).

## What it knows about every shot

- **Shots, not files.** Every file is split into shots (hard cuts, dissolves, fades) and long takes into segments, each
  with its own record.
- **How it was filmed.** Shot size, camera angle and movement (from optical flow), lens, depth of field, lighting, colour
  grade, speed effects, resolution, frame rate, HDR and log.
- **What it shows.** SigLIP embeddings and zero-shot labels for setting, time of day, weather, season and mood; objects,
  people and on-screen text (OCR); optional dense captions from a vision-language model.
- **What is said.** Speech with word timings (Parakeet), speaker turns, audio events and loudness (EBU R128).
- **What it's for.** Shot role, pace, cuts per minute, usability, and whether a file is a raw take, selects or a finished
  edit.
- **Who is in it.** Faces are recognised across shots and files, locally. Name someone once and "Maria laughing in the
  kitchen" finds them. Merge, split or forget people at any time.
- **Whether you can use it.** Source, licence, permitted uses, channels, territories, expiry and releases per file
  (overridable per shot). State an intended use and you only get shots cleared for it.

Search blends semantic similarity, keywords in transcripts and on-screen text, and label matches. Natural language is
parsed into filters you can see and edit, and every result says *why* it matched. Query by example with a shot, a still
or a clip. Corrections are stored separately from machine output and win over it, even after re-processing.

Footage can come from folders, S3 buckets, or web links: paste YouTube, Vimeo or other links (or a whole playlist) and
they are downloaded with yt-dlp and analysed like everything else, with rights starting as unknown. Hosted models
(an OpenAI API key, OpenRouter, or a ChatGPT subscription via the Codex CLI) add richer captions and much higher throughput
once an admin enables one.

## Screenshots

| | |
|---|---|
| ![Search with parsed query chips, results and why each shot matched](review/m4/screens/01-search-results--desktop-light.jpg) | ![Shot detail with every signal, its source and confidence](review/m4/screens/02-shot-detail--desktop-dark.jpg) |
| Search: the query becomes editable chips; every result explains why it matched | Shot detail: each signal shows its source and confidence; corrections are marked human |
| ![Library overview with edit stage, rights and coverage gaps](review/m4/screens/04-library-overview--desktop-light.jpg) | ![Send a collection to Cutawan](review/m4/screens/06-send-to-cutawan-dialog--desktop-dark.jpg) |
| Library overview: edit stage, rights, coverage gaps | Collections go to Cutawan or out as OTIO / FCPXML / EDL |

All journeys, at desktop, laptop and tablet sizes in light and dark: [review/m4](review/m4/index.md).

## Quick start

**Server or NAS (Docker):**

```bash
git clone https://github.com/JeremySNR/Metachlorian && cd Metachlorian
METACHLORIAN_ADMIN_PASSWORD='choose-a-long-password' FOOTAGE_DIR=/path/to/footage \
  docker compose -f deploy/docker-compose.yml up -d
# open http://<host>:8765 and sign in as admin
```

**One command (Linux/macOS, Docker or native):**

```bash
curl -fsSL https://raw.githubusercontent.com/JeremySNR/Metachlorian/main/scripts/install.sh | bash
```

**From source (solo mode on your machine):**

```bash
cd core && uv venv -p 3.11 && uv pip install -e ".[analysis]"
.venv/bin/metachlorian models fetch            # local models, ~1.9 GB
.venv/bin/metachlorian serve --add ~/Footage   # http://127.0.0.1:8765
cd ../app && npm ci && npm run build           # the web app the core serves
```

**Desktop app:** `cd desktop && npm ci && npm start` runs the web app in Electron. In solo mode it starts a local core; in team
mode it connects to a shared one. It adds native drag-out of real clip files and one-click hand-off to Cutawan. Installers are
built with `npm run package` (unsigned until signing certificates are provided, see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)).

## Community sharing

Metachlorian can also search a public [community index](https://metachlorian-community.vercel.app) of analysed YouTube
videos and open results at the matching timestamp.

YouTube imports have a separate, default-on sharing setting from hosted model analysis. After analysis finishes,
the app sends only the machine metadata allowlist and download title/channel/licence/duration to the community service.
Videos, frames, audio files and complete library records are never contributed. Local and personal files, local
duplicates, human notes and face identities are excluded.

**Warning: video visibility is not checked.** Private, unlisted or sensitive YouTube imports can publish their titles,
descriptions, transcripts and on-screen text. Turn off **Settings → Community sharing** before importing them if you
want that metadata to stay private. Published metadata can remain searchable after the original video becomes private
or is deleted. Opting out stops pending contributions; it does not remove already published metadata.

The default service is `https://metachlorian-community.vercel.app`; its [source and deployment guide](https://github.com/JeremySNR/Metachlorian-community)
live in a separate repository and database. No YouTube API key or Google Cloud setup is required.
Community search sends your query to that service and opens results at matching YouTube timestamps.
Analysis and contributor-reported licences may be wrong and do not establish reuse rights.
The community operator can remove a video from the index.

Turn sharing off in **Settings → Community sharing**, or set `METACHLORIAN_COMMUNITY_ENABLED=false` before starting the app.
`METACHLORIAN_COMMUNITY_URL` selects a self-hosted service (HTTPS required except on loopback).
Videos imported while sharing is off are never backfilled; turning it off also suppresses pending updates.
Only newly downloaded YouTube bytes are enrolled, so existing libraries, local/personal files, other websites and local
duplicates are never uploaded automatically. Replaced or deleted downloads are excluded.
Network failures leave contributions pending for retry; local analysis continues normally.
`metachlorian community-sync` retries a bounded batch without running the web server.

## Hardware tiers

| Tier | What runs | Speed (this build's reference box: 4 vCPU, no GPU) |
|---|---|---|
| CPU only | Everything except VLM captions: shots, motion, quality, audio, speech, OCR, people, embeddings, zero-shot labels, rules-based fusion | **1.7 hours of footage per hour** with 3 workers; search median 325 ms at 1.6 M shots ([eval](eval/README.md)) |
| Single consumer GPU (8–12 GB) | Adds a local VLM (Qwen3.5 4B/9B via llama.cpp or Ollama) for dense captions and LLM fusion; ONNX models use CUDA | GPU numbers to be measured by maintainers (no GPU in the build environment) |
| Multi-GPU / server | Several workers (`workers = N`), a larger VLM, team mode with many users | scales with workers |

## How it fits together

```
 folders / S3 ──▶ ingest (hash, dedupe, ffprobe) ──▶ job queue (SQLite, resumable, versioned analysers)
                                                         │
     technical → proxy → shots → keyframes → embed → zero-shot tags
                                     ├─▶ motion, quality, people, OCR
                                     └─▶ audio → speech ──▶ caption (VLM, optional) ──▶ fusion ──▶ rollup
                                                         │
                         SQLite (records, FTS5) + usearch HNSW (vectors) ──▶ hybrid search
                                                         │
                       REST API · MCP server · web app · Electron shell · Cutawan / OTIO / FCPXML / EDL
```

Read more: [architecture](docs/architecture.md) · [decision records](docs/decisions) · [design system](docs/design/system.md) ·
[evaluation](eval/README.md) · [licences](docs/licences.md) · [Cutawan hand-off](docs/integration/cutawan-contract.md) ·
[plan](PLAN.md) · [roadmap](docs/roadmap.md) · [open questions](OPEN_QUESTIONS.md).

## Licence

Apache-2.0. Model weights have their own licences (all permit commercial use); see [docs/licences.md](docs/licences.md) and
[NOTICE](NOTICE).
