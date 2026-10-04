"""Verify visibility anonymously. Missing visibility, unlisted and login-only videos fail closed."""
from __future__ import annotations

import json
import subprocess

from ..config import Settings
from ..ingest import ytdlp
from .protocol import youtube_url


class NotPublic(ValueError):
    pass


def verify_public(video_id: str, settings: Settings) -> dict:
    url = youtube_url(video_id)
    # Ignore user/system yt-dlp configuration and plugins. Never borrow cookies, proxy settings or a browser login.
    exe = ytdlp.find(settings)
    if not exe:
        raise RuntimeError("Install yt-dlp before verifying public videos")
    result = subprocess.run([exe, "--ignore-config", "--no-plugin-dirs", "--no-warnings", "--skip-download", "--no-playlist",
                             "--socket-timeout", "10", "--retries", "0", "-J", "--", url],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        # Transient extractor/network failures must not be treated as proof of public visibility.
        raise RuntimeError("Anonymous YouTube visibility check could not complete")
    data = json.loads(result.stdout)
    if (data.get("id") != video_id or (data.get("extractor_key") or "").lower() != "youtube" or
            data.get("availability") != "public" or data.get("is_live") or data.get("live_status") in ("is_live", "is_upcoming")):
        raise NotPublic("Video is not explicitly public on YouTube")
    # The service obtains these from YouTube, not from a contributor's local title or notes.
    return {"title": str(data.get("title") or "YouTube video")[:500],
            "channel": str(data.get("channel") or data.get("uploader") or "")[:300],
            "license": str(data.get("license") or "")[:500], "duration": data.get("duration")}
