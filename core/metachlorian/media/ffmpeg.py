"""Thin, dependency-free wrappers around ffmpeg / ffprobe."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np


def _bin(name: str) -> str:
    env = os.environ.get(f"METACHLORIAN_{name.upper()}")
    if env:
        return env
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{name} not found on PATH. Install FFmpeg (https://ffmpeg.org) or set METACHLORIAN_{name.upper()}.")
    return found


def ffmpeg_bin() -> str:
    return _bin("ffmpeg")


def ffprobe_bin() -> str:
    return _bin("ffprobe")


def run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run(args, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        err = p.stderr.decode(errors="replace")[-2000:]
        raise RuntimeError(f"{Path(args[0]).name} failed ({p.returncode}): {err}")
    return p


def ffprobe(path: str | Path) -> dict[str, Any]:
    p = run([ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", str(path)], timeout=120)
    return json.loads(p.stdout)


def _ratio(s: str | None) -> float | None:
    if not s or s in ("0/0", "N/A"):
        return None
    if "/" in s:
        a, b = s.split("/", 1)
        try:
            a_f, b_f = float(a), float(b)
            return a_f / b_f if b_f else None
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


_ISO6709 = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?")

HDR_TRANSFERS = {"smpte2084": "PQ (HDR10)", "arib-std-b67": "HLG"}
LOG_HINTS = ("log", "slog", "s-log", "clog", "c-log", "vlog", "v-log", "flog", "f-log", "nlog", "n-log", "logc", "apple log", "dlog", "d-log", "hlg")


def technical_metadata(path: str | Path) -> dict[str, Any]:
    """Deterministic technical metadata from ffprobe (and exiftool when present)."""
    info = ffprobe(path)
    fmt = info.get("format", {})
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    tags = {k.lower(): v_ for k, v_ in (fmt.get("tags") or {}).items()}
    if v:
        tags.update({k.lower(): v_ for k, v_ in (v.get("tags") or {}).items() if k.lower() not in tags})
    out: dict[str, Any] = {
        "container": fmt.get("format_name"),
        "duration": float(fmt["duration"]) if fmt.get("duration") not in (None, "N/A") else None,
        "size": int(fmt["size"]) if fmt.get("size") else Path(path).stat().st_size,
        "bitrate": int(fmt["bit_rate"]) if fmt.get("bit_rate") not in (None, "N/A") else None,
        "has_video": v is not None,
        "audio_streams": len(audio),
        "chapters": len(info.get("chapters", [])),
    }
    if v:
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        if "rotate" in tags:
            try:
                rot = int(tags["rotate"])
            except ValueError:
                pass
        if abs(rot) % 180 == 90:
            w, h = h, w
        sar = _ratio(v.get("sample_aspect_ratio")) or 1.0
        display_w = w * sar if sar and sar > 0 else w
        fps = _ratio(v.get("avg_frame_rate")) or _ratio(v.get("r_frame_rate"))
        rfps = _ratio(v.get("r_frame_rate"))
        transfer = v.get("color_transfer")
        pix = v.get("pix_fmt") or ""
        bit_depth = int(v["bits_per_raw_sample"]) if str(v.get("bits_per_raw_sample", "")).isdigit() else (10 if "10" in pix else 12 if "12" in pix else 8)
        nb_frames = int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None
        out.update({
            "width": w, "height": h, "rotation": rot,
            "aspect_ratio": round(display_w / h, 4) if h else None,
            "orientation": "vertical" if h > display_w else "square" if abs(h - display_w) < 2 else "horizontal",
            "fps": round(fps, 3) if fps else None,
            "variable_frame_rate": bool(fps and rfps and abs(fps - rfps) > 0.01 * rfps),
            "frame_count": nb_frames,
            "video_codec": v.get("codec_name"), "video_profile": v.get("profile"),
            "pix_fmt": pix, "bit_depth": bit_depth,
            "chroma": "4:4:4" if "444" in pix else "4:2:2" if "422" in pix else "4:2:0" if pix else None,
            "color_primaries": v.get("color_primaries"), "color_transfer": transfer,
            "color_space": v.get("color_space"), "color_range": v.get("color_range"),
            "hdr": transfer in HDR_TRANSFERS, "hdr_format": HDR_TRANSFERS.get(transfer or ""),
            "video_bitrate": int(v["bit_rate"]) if str(v.get("bit_rate", "")).isdigit() else None,
            "resolution_class": resolution_class(w, h),
            "interlaced": (v.get("field_order") or "progressive") not in ("progressive", "unknown"),
            "timecode": tags.get("timecode"),
        })
    if audio:
        a = audio[0]
        out.update({
            "audio_codec": a.get("codec_name"),
            "audio_channels": int(a.get("channels") or 0),
            "audio_layout": a.get("channel_layout"),
            "audio_sample_rate": int(a.get("sample_rate") or 0),
        })
    else:
        out.update({"audio_channels": 0})
    # Camera / capture metadata from container tags.
    make = tags.get("com.apple.quicktime.make") or tags.get("make") or tags.get("manufacturer")
    model = tags.get("com.apple.quicktime.model") or tags.get("model")
    lens = tags.get("com.apple.quicktime.camera.lens_model") or tags.get("lens") or tags.get("lens_model")
    created = tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time") or tags.get("date")
    loc = tags.get("com.apple.quicktime.location.iso6709") or tags.get("location") or tags.get("location-eng")
    gps = None
    if loc and (m := _ISO6709.match(loc)):
        gps = {"lat": float(m.group(1)), "lon": float(m.group(2)), "alt": float(m.group(3)) if m.group(3) else None}
    out.update({"camera_make": make, "camera_model": model, "lens": lens, "capture_date": created, "gps": gps,
                "encoder": tags.get("encoder") or tags.get("handler_name")})
    out.update(_exiftool(path))
    # Log/flat profile hint from metadata only; image statistics refine it later.
    hint_src = " ".join(str(x) for x in (tags.get("com.apple.quicktime.camera.identifier"), tags.get("gamma"), tags.get("comment"), transfer, out.get("video_profile")) if x).lower()
    out["log_hint"] = next((h for h in LOG_HINTS if h != "hlg" and h in hint_src), None)
    out["tags"] = {k: v_ for k, v_ in tags.items() if len(str(v_)) < 200}
    return out


def _exiftool(path: str | Path) -> dict[str, Any]:
    exe = shutil.which("exiftool")
    if not exe:
        return {}
    try:
        p = subprocess.run([exe, "-j", "-n", "-Make", "-Model", "-LensModel", "-LensID", "-FocalLength", "-GPSLatitude", "-GPSLongitude",
                            "-CreateDate", "-DateTimeOriginal", "-GammaCurve", "-CaptureGammaEquation", "-ColorPrimaries", str(path)],
                           capture_output=True, timeout=60)
        d = json.loads(p.stdout or b"[{}]")[0]
    except Exception:
        return {}
    out: dict[str, Any] = {}
    if d.get("Make"):
        out["camera_make"] = d["Make"]
    if d.get("Model"):
        out["camera_model"] = d["Model"]
    if d.get("LensModel") or d.get("LensID"):
        out["lens"] = d.get("LensModel") or d.get("LensID")
    if d.get("FocalLength"):
        out["focal_length_mm"] = d["FocalLength"]
    if d.get("GPSLatitude") is not None and d.get("GPSLongitude") is not None:
        out["gps"] = {"lat": d["GPSLatitude"], "lon": d["GPSLongitude"], "alt": None}
    if d.get("DateTimeOriginal") or d.get("CreateDate"):
        out["capture_date"] = d.get("DateTimeOriginal") or d.get("CreateDate")
    gamma = (str(d.get("GammaCurve") or "") + " " + str(d.get("CaptureGammaEquation") or "")).strip()
    if gamma:
        out["gamma"] = gamma
    return out


def resolution_class(w: int, h: int) -> str:
    long_edge, short_edge = max(w, h), min(w, h)
    if long_edge >= 7680 or short_edge >= 4320:
        return "8k"
    if long_edge >= 5000:
        return "6k"
    if long_edge >= 3800 or short_edge >= 2100:
        return "4k"
    if long_edge >= 2500:
        return "2.7k"
    if long_edge >= 1900 or short_edge >= 1080:
        return "hd1080"
    if long_edge >= 1270 or short_edge >= 720:
        return "hd720"
    return "sd"


# ---------------------------------------------------------------- renditions

def make_proxy(src: str | Path, dst: str | Path, height: int = 540, crf: int = 26, fps_cap: float = 30.0,
               src_fps: float | None = None) -> None:
    """H.264 proxy with a 1 s GOP for instant seeking/scrubbing, faststart for streaming."""
    dst = Path(dst)
    tmp = dst.with_suffix(".tmp.mp4")
    gop = max(1, int(round(min(src_fps or fps_cap, fps_cap))))
    vf = f"scale=-2:'min({height},ih)':flags=bicubic,format=yuv420p"
    if src_fps and src_fps > fps_cap + 0.5:
        vf = f"fps={fps_cap}," + vf
    args = [ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-g", str(gop), "-keyint_min", str(gop),
            "-sc_threshold", "0", "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", "-map_metadata", "-1", str(tmp)]
    run(args)
    tmp.replace(dst)


def extract_audio(src: str | Path, dst: str | Path, rate: int = 16000) -> bool:
    """Mono PCM WAV for speech and audio analysis. Returns False when there is no audio."""
    try:
        run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(dst)])
        return Path(dst).exists() and Path(dst).stat().st_size > 1000
    except RuntimeError as e:
        if "matches no streams" in str(e) or "does not contain any stream" in str(e):
            return False
        raise


def read_wav_mono(path: str | Path) -> tuple[np.ndarray, int]:
    import wave

    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
    return data, rate


def iter_frames(src: str | Path, width: int, height: int, fps: float | None = None, gray: bool = False,
                start: float | None = None, duration: float | None = None) -> Iterator[np.ndarray]:
    """Stream decoded frames as numpy arrays at a fixed small size."""
    pix = "gray" if gray else "rgb24"
    ch = 1 if gray else 3
    vf = f"scale={width}:{height}:flags=area"
    if fps:
        vf = f"fps={fps}," + vf
    args = [ffmpeg_bin(), "-v", "error"]
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    args += ["-map", "0:v:0", "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "-"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=width * height * ch * 8)
    size = width * height * ch
    try:
        assert proc.stdout is not None
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            arr = np.frombuffer(buf, dtype=np.uint8)
            yield arr.reshape(height, width) if gray else arr.reshape(height, width, 3)
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.kill()
        proc.wait()


def frame_at(src: str | Path, t: float, width: int | None = None) -> np.ndarray:
    """One RGB frame at time t (accurate seek)."""
    vf = f"scale={width}:-2:flags=bicubic" if width else "null"
    args = [ffmpeg_bin(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1", "-vf", vf,
            "-f", "image2pipe", "-vcodec", "png", "-"]
    p = run(args)
    import cv2

    img = cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"could not decode frame at {t}s from {src}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def frames_at(src: str | Path, times: list[float], width: int | None = None) -> list[np.ndarray]:
    return [frame_at(src, t, width) for t in times]


def save_jpeg(rgb: np.ndarray, path: str | Path, quality: int = 85, width: int | None = None) -> None:
    import cv2

    img = rgb
    if width and img.shape[1] != width:
        h = int(round(img.shape[0] * width / img.shape[1] / 2) * 2)
        img = cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    Path(path).write_bytes(buf.tobytes())


@dataclass
class SpriteInfo:
    interval: float
    tile_w: int
    tile_h: int
    cols: int
    rows: int
    count: int
    sheets: list[str]

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def make_sprites(src: str | Path, out_dir: str | Path, duration: float, interval: float = 1.0, tile_w: int = 192,
                 aspect: float = 16 / 9, cols: int = 10, rows: int = 10) -> SpriteInfo:
    """Sprite sheets of frames every ``interval`` seconds, for instant hover scrubbing."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Keep the sheet count small for long files by widening the interval.
    count = max(1, int(math.ceil(duration / interval)))
    if count > 2000:
        interval = duration / 2000
        count = 2000
    tile_h = int(round(tile_w / max(aspect, 0.2) / 2) * 2)
    per = cols * rows
    for old in out_dir.glob("sprite_*.jpg"):
        old.unlink()
    vf = (f"fps=1/{interval},scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease:flags=area,"
          f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2:color=black,tile={cols}x{rows}")
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-vf", vf, "-q:v", "5", str(out_dir / "sprite_%03d.jpg")])
    sheets = sorted(p.name for p in out_dir.glob("sprite_*.jpg"))
    return SpriteInfo(interval=interval, tile_w=tile_w, tile_h=tile_h, cols=cols, rows=rows,
                      count=min(count, len(sheets) * per), sheets=sheets)


def loudness(src: str | Path) -> dict[str, Any]:
    """EBU R128 integrated loudness, range and true peak, plus a 100 ms momentary curve."""
    p = subprocess.run([ffmpeg_bin(), "-v", "info", "-nostats", "-i", str(src), "-map", "0:a:0", "-af", "ebur128=peak=true:framelog=verbose",
                        "-f", "null", "-"], capture_output=True, timeout=3600)
    err = p.stderr.decode(errors="replace")
    momentary: list[tuple[float, float]] = []
    for m in re.finditer(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-inf)", err):
        t = float(m.group(1))
        val = m.group(2)
        momentary.append((t, -120.0 if val == "-inf" else float(val)))
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else ""

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, summary)
        if not m:
            return None
        return None if m.group(1) == "-inf" else float(m.group(1))

    return {
        "integrated_lufs": grab(r"I:\s*(-?[\d.]+|-inf) LUFS"),
        "loudness_range_lu": grab(r"LRA:\s*(-?[\d.]+) LU"),
        "true_peak_dbfs": grab(r"Peak:\s*(-?[\d.]+|-inf) dBFS"),
        "momentary": momentary,
    }


def render_clip(src: str | Path, dst: str | Path, start: float, end: float, reencode: bool = True, height: int | None = None) -> None:
    dur = max(0.04, end - start)
    if reencode:
        vf = ["-vf", f"scale=-2:{height}"] if height else []
        args = [ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}", *vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(dst)]
    else:
        args = [ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}", "-c", "copy",
                "-avoid_negative_ts", "make_zero", str(dst)]
    run(args)
