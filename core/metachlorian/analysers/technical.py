from __future__ import annotations

from typing import Any

from ..media import ffmpeg
from .base import AnalysisContext, Analyser

ASSET_FIELDS = ("duration", "width", "height", "fps", "aspect_ratio", "orientation", "resolution_class", "video_codec", "video_profile",
                "bit_depth", "chroma", "bitrate", "video_bitrate", "color_primaries", "color_transfer", "color_space", "hdr", "hdr_format",
                "audio_channels", "audio_codec", "audio_sample_rate", "size", "camera_make", "camera_model", "lens", "focal_length_mm",
                "capture_date", "gps", "timecode", "variable_frame_rate", "interlaced", "container")


class TechnicalAnalyser(Analyser):
    name = "technical"
    version = "1.0.0"
    priority = 100
    description = "Container, stream, colour and camera metadata via ffprobe (and exiftool when installed). Deterministic."

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        tech = ffmpeg.technical_metadata(ctx.source_path)
        if not tech.get("has_video"):
            raise ValueError("file has no video stream")
        ctx.asset_updates.update({"tech": tech, "duration": tech.get("duration"), "width": tech.get("width"),
                                  "height": tech.get("height"), "fps": tech.get("fps")})
        ctx.asset["tech"] = tech
        for f in ASSET_FIELDS:
            if tech.get(f) is not None:
                ctx.asset_signal(f"tech.{f}", tech[f], 1.0)
        return {"duration": tech.get("duration"), "resolution": f"{tech.get('width')}x{tech.get('height')}", "fps": tech.get("fps")}
