from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..media import ffmpeg
from .base import AnalysisContext, Analyser, CannotDecode

RAW_HELP = {
    "Blackmagic RAW": "Blackmagic's RAW SDK or DaVinci Resolve",
    "RED R3D": "RED's REDline command-line tool",
    "ARRIRAW": "ARRI Reference Tool (command line)",
    "ARRIRAW HDE": "ARRI Reference Tool (command line)",
    "Canon Cinema RAW Light": "Canon RAW Development or DaVinci Resolve",
    "Nikon N-RAW": "Nikon's tools or DaVinci Resolve",
    "MotionCam RAW": "MotionCam Tools",
}

ASSET_FIELDS = ("duration", "width", "height", "fps", "aspect_ratio", "orientation", "resolution_class", "video_codec", "video_profile",
                "bit_depth", "chroma", "bitrate", "video_bitrate", "color_primaries", "color_transfer", "color_space", "hdr", "hdr_format",
                "audio_channels", "audio_codec", "audio_sample_rate", "size", "camera_make", "camera_model", "lens", "focal_length_mm",
                "capture_date", "gps", "timecode", "variable_frame_rate", "interlaced", "container")


class TechnicalAnalyser(Analyser):
    name = "technical"
    version = "1.1.0"
    priority = 100
    description = "Container, stream, colour and camera metadata via ffprobe (and exiftool when installed). Deterministic."

    def config(self, settings) -> dict[str, Any]:
        # A new or changed raw decoder re-runs this (and so everything after it) for that format.
        return {"raw_decoders": dict(sorted((settings.raw_decoders or {}).items()))}

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        from ..ingest.scan import RAW_EXTS

        ext = Path(ctx.asset["path"]).suffix.lower()
        decoded = None
        if ext in RAW_EXTS:
            decoded = self._decode_raw(ctx, ext, RAW_EXTS[ext])
            src = decoded
        else:
            src = ctx.source_path
        try:
            tech = ffmpeg.technical_metadata(src)
        except RuntimeError as e:
            # Name the file, never the server's folders (everyone who can see the file sees this message).
            why = (str(e).strip().splitlines() or ["unknown format"])[-1].replace(str(src), Path(src).name)[-200:]
            raise CannotDecode(f"FFmpeg cannot read this file ({why}). "
                               "If it is camera raw, set a raw decoder for its extension in Settings → Formats, or export a "
                               "ProRes/DNx copy into a watched folder.") from e
        if not tech.get("has_video"):
            raise CannotDecode("file has no video stream")
        if not tech.get("video_codec") or tech.get("video_codec") == "none":
            raise CannotDecode("FFmpeg has no decoder for this file's video (camera raw inside MXF/MOV, e.g. Sony X-OCN, ARRIRAW "
                               "or ProRes RAW). Set a raw decoder in Settings → Formats, or export a ProRes/DNx copy.")
        if decoded:
            tech["decoded_from"] = {"format": RAW_EXTS[ext], "master": str(decoded), "decoder": (ctx.settings.raw_decoders or {}).get(ext[1:])}
        ctx.asset_updates.update({"tech": tech, "duration": tech.get("duration"), "width": tech.get("width"),
                                  "height": tech.get("height"), "fps": tech.get("fps")})
        ctx.asset["tech"] = tech
        if decoded:
            ctx.asset_updates["local_path"] = str(decoded)  # every later step reads the decoded master
        for f in ASSET_FIELDS:
            if tech.get(f) is not None:
                ctx.asset_signal(f"tech.{f}", tech[f], 1.0)
        return {"duration": tech.get("duration"), "resolution": f"{tech.get('width')}x{tech.get('height')}", "fps": tech.get("fps")}

    def _decode_raw(self, ctx: AnalysisContext, ext: str, fmt: str) -> Path:
        """Convert camera raw to a working master with the configured vendor tool (once per file)."""
        tmpl = (ctx.settings.raw_decoders or {}).get(ext[1:])
        if not tmpl:
            raise CannotDecode(f"{fmt} can only be decoded with the camera maker's software ({RAW_HELP.get(fmt, 'the maker’s tools')}). "
                               f"Set a raw decoder command for .{ext[1:]} in Settings → Formats, or export a ProRes/DNx copy into a "
                               "watched folder.")
        out_dir = ctx.work_dir / "master"
        out = out_dir / "master.mov"
        if out.exists() and ctx.asset.get("local_path") == str(out):
            return out  # already decoded for this content (a content change clears local_path)
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True)
        src = Path(ctx.asset.get("local_path") or ctx.asset["path"])
        if src.parent == out_dir.parent:
            src = Path(ctx.asset["path"])
        values = {"input": str(src), "output": str(out), "output_stem": str(out.with_suffix("")), "output_dir": str(out_dir)}
        argv = [a.format(**values) for a in shlex.split(tmpl)]
        try:
            p = subprocess.run(argv, capture_output=True, timeout=12 * 3600, cwd=out_dir)
        except FileNotFoundError as e:
            raise CannotDecode(f"The raw decoder for .{ext[1:]} is not installed or not on PATH: {argv[0]}") from e
        except subprocess.TimeoutExpired as e:
            raise CannotDecode(f"The raw decoder for .{ext[1:]} did not finish within 12 hours") from e
        if not out.exists():
            # Some tools choose their own file name: take the one video they wrote.
            made = sorted((f for f in out_dir.iterdir() if f.is_file() and f.suffix.lower() in (".mov", ".mxf", ".mp4")),
                          key=lambda f: -f.stat().st_size)
            if made:
                os.replace(made[0], out)
        if p.returncode != 0 or not out.exists():
            err = (p.stderr or p.stdout).decode(errors="replace").strip()[-400:].replace(str(src), src.name).replace(str(out_dir), "…")
            raise CannotDecode(f"The raw decoder for .{ext[1:]} failed (exit {p.returncode}): {err or 'no output file'}")
        return out
