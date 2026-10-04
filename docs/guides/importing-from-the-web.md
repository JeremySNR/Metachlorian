# Importing videos from web links

Metachlorian can download videos from YouTube, Vimeo, the Internet Archive, direct video links and the
[thousand-plus sites yt-dlp supports](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md), then analyse them like any
other file. It is the same importer Cutawan uses, ported to the core.

**In the app:** Ingest → *Add from links*. Paste one or more links, choose a folder (e.g. `Disney 2026`), a quality cap, and
whether a playlist or channel link should import every video.

**From the command line:**

```sh
metachlorian import "https://www.youtube.com/watch?v=…" --folder "Disney 2026"
metachlorian import "https://www.youtube.com/playlist?list=…" --playlist --max-height 2160
```

**API:** `POST /api/imports` with `{"urls": [...], "folder": "Disney 2026", "playlist": false, "max_height": 1080}`;
progress at `GET /api/imports`. Needs the `ingest:write` scope (editors and admins; not agents).

## Where files go

`<library>/imports/<folder>/<title> [<video id>].mp4`. Without a folder, the site's name is used (`YouTube`, `Vimeo`…); a
playlist goes to `<site>/<playlist title>`. They appear in Library → Folders, so you can search inside them, and the file's
date is set to the upload date. The same video imported twice is recognised and not downloaded again.

Each file remembers where it came from — link, title, channel, upload date, the licence the site states, tags — and the
title, channel and tags are searchable.

## Rights

Imported files start with rights **unknown**, with the link, the channel as owner, and the site's stated licence in the
notes. Being online, or labelled Creative Commons by whoever uploaded it, is not clearance, so a person has to check and mark
it cleared. Until then agents do not see it. Only import videos you have the right to use, and check the site's terms.

## Private, unlisted and members-only videos

yt-dlp can borrow a login:

- **cookies.txt** (works everywhere, recommended for servers): sign in to the site in your browser, export cookies with the
  *Get cookies.txt LOCALLY* extension, and upload the file in Settings → Imports. It is stored readable only by the server
  and never sent back by the API.
- **Browser login** (solo / desktop only, because it reads the browser on the machine running Metachlorian): choose the
  browser in Settings → Imports. On Windows, Chrome and Edge encrypt their cookies so other programs cannot read them; use a
  cookies.txt file or Firefox there.

## The yt-dlp program

If `yt-dlp` is on the server's PATH (or set in Settings → Imports) it is used; otherwise the official standalone build is
downloaded into `<library>/bin` on first use. Sites change often, so when a download fails Metachlorian lets yt-dlp update
itself once and retries. In team mode, links to addresses on the server's own network are refused.
