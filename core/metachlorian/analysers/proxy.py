from __future__ import annotations

from typing import Any

from ..db import loads
from ..media import ffmpeg
from .base import AnalysisContext, Analyser


class ProxyAnalyser(Analyser):
    name = "proxy"
    version = "1.1.0"
    requires = ("technical",)
    priority = 95
    description = ("Lightweight H.264 proxy (1 s GOP for instant seeking) converted to SDR BT.709 from any bit depth, chroma or colour "
                   "space (HDR tone-mapped, interlaced deinterlaced), 16 kHz mono audio for analysis, and sprite sheets for hover scrubbing.")

    def config(self, settings) -> dict[str, Any]:
        return {"h": settings.proxy_height, "crf": settings.proxy_crf, "sprite": settings.sprite_interval}

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        tech = loads(ctx.db.q1("SELECT tech FROM assets WHERE id=?", (ctx.asset["id"],))["tech"], {})
        src = ctx.source_path
        conv = ffmpeg.make_proxy(src, ctx.proxy_path, ctx.settings.proxy_height, ctx.settings.proxy_crf, src_fps=tech.get("fps"), tech=tech)
        if conv["decode_errors"]:
            # Parts of the file could not be read: say so instead of silently showing glitches or black.
            ctx.asset_signal("quality.decode_errors", conv["decode_errors"], 1.0)
        has_audio = False
        if tech.get("audio_channels"):
            has_audio = ffmpeg.extract_audio(src, ctx.audio_path)
        elif ctx.audio_path.exists():
            ctx.audio_path.unlink()
        aspect = tech.get("aspect_ratio") or 16 / 9
        sprites = ffmpeg.make_sprites(ctx.proxy_path, ctx.work_dir / "sprites", tech.get("duration") or 0, ctx.settings.sprite_interval,
                                      aspect=aspect)
        poster = ctx.work_dir / "poster.jpg"
        dur = tech.get("duration") or 0
        frame = ffmpeg.frame_at(ctx.proxy_path, min(dur * 0.1, 5.0) if dur else 0, 640)
        ffmpeg.save_jpeg(frame, poster, 82)
        return {"proxy": "proxy.mp4", "proxy_bytes": ctx.proxy_path.stat().st_size, "has_audio": has_audio, **conv,
                "sprites": sprites.as_dict(), "poster": "poster.jpg"}
