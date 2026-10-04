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
    if out.get("hdr"):
        out["max_luminance"] = hdr_peak_nits(path)
    return out


def hdr_peak_nits(path: str | Path) -> float | None:
    """Content peak brightness of HDR10 video: MaxCLL, else the mastering display's peak (first frame's side data)."""
    try:
        p = run([ffprobe_bin(), "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+#1", "-show_frames",
                 "-show_entries", "frame=side_data_list", "-of", "json", str(path)], timeout=60)
        sds = [sd for f in json.loads(p.stdout).get("frames", []) for sd in f.get("side_data_list", []) or []]
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        return None
    cll = next((float(sd["max_content"]) for sd in sds if sd.get("max_content")), None)
    mastering = next((_ratio(sd.get("max_luminance")) for sd in sds if sd.get("max_luminance")), None)
    peak = cll or mastering
    return round(peak, 1) if peak and 100 < peak <= 10000 else None


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

# ---------------------------------------------------------------------- display conversion
# Everything people look at and every model reads is the proxy, so the proxy is display-referred SDR
# BT.709 whatever the source: any bit depth (8-16 bit, float), chroma (4:2:0 / 4:2:2 / 4:4:4, alpha),
# matrix, range or transfer. HDR (PQ, HLG) is tone-mapped per BT.2408: reference white 203 nits maps to SDR
# white, and highlights up to the stream's peak (or 1000 nits) roll off softly above 70%.
REFERENCE_WHITE_NITS = 203
# ffprobe's colour names that zscale accepts as-is; the few it does not know are translated.
_MATRIX = {"bt709", "fcc", "bt470bg", "smpte170m", "smpte240m", "ycgco", "bt2020nc", "bt2020c", "chroma-derived-nc",
           "chroma-derived-c", "ictcp"}
_PRIM = {"bt709", "bt470m", "bt470bg", "smpte170m", "smpte240m", "film", "bt2020", "smpte428", "smpte431", "smpte432",
         "jedec-p22", "ebu3213"}
_TRC = {"bt709", "smpte170m", "smpte240m", "bt470m", "bt470bg", "linear", "log100", "log316", "iec61966-2-4",
        "iec61966-2-1", "bt2020-10", "bt2020-12", "smpte2084", "arib-std-b67"}
_TRC_ALIAS = {"gamma22": "bt470m", "gamma28": "bt470bg", "bt1361e": "bt709", "smpte428": "bt709"}
_HDR_TRC = {"smpte2084", "arib-std-b67"}


def _is_rgb(pix: str) -> bool:
    return pix.startswith(("gbr", "rgb", "bgr", "argb", "abgr", "0rgb", "0bgr", "x2rgb", "x2bgr"))


def display_filter(tech: dict[str, Any], height: int | None = None, peak_nits: float | None = None) -> str:
    """ffmpeg filter chain: any source -> 8-bit 4:2:0 SDR BT.709, limited range, progressive, scaled to ``height``."""
    pix = tech.get("pix_fmt") or ""
    h = int(tech.get("height") or 1080)
    sd = h <= 576
    parts: list[str] = []
    if tech.get("interlaced"):
        parts.append("bwdif=mode=send_frame:deint=interlaced")
    if height:
        parts.append(f"scale=-2:'min({height},ih)':flags=bicubic")
    if "a" in pix.replace("gray", "").split("p")[0] or pix.startswith(("yuva", "gbrap", "rgba", "bgra", "argb", "abgr", "ya")):
        parts.append("format=gbrp16le" if _is_rgb(pix) else "format=yuv444p16le")  # drop alpha (premultiplied: over black)
    rgb = _is_rgb(pix)
    jpeg = pix.startswith("yuvj")
    t_in = _TRC_ALIAS.get(tech.get("color_transfer") or "", tech.get("color_transfer"))
    trc = t_in if t_in in _TRC else "bt709"
    p_in = tech.get("color_primaries")
    # Untagged: SD is BT.601 (PAL or NTSC primaries), HD and up BT.709 — what players assume.
    hdr = trc in _HDR_TRC
    prim = p_in if p_in in _PRIM else ("bt2020" if hdr else "bt470bg" if sd and h in (576, 288) else "smpte170m" if sd else "bt709")
    rng = {"pc": "full", "jpeg": "full", "tv": "limited", "mpeg": "limited"}.get(tech.get("color_range") or "",
                                                                                "full" if rgb or jpeg else "limited")
    m_in = tech.get("color_space")
    mat = "gbr" if rgb else m_in if m_in in _MATRIX else ("bt2020nc" if hdr else "smpte170m" if sd or jpeg else "bt709")
    # Stamp the (normalised) description on the frames once, so every conversion step agrees, even for untagged files.
    parts.append(f"setparams=color_primaries={prim}:color_trc={trc}:colorspace={mat}:range={'pc' if rng == 'full' else 'tv'}")
    if hdr:
        peak = max(1.0, (peak_nits or tech.get("max_luminance") or 1000.0) / REFERENCE_WHITE_NITS)
        parts += [f"zscale=t=linear:npl={REFERENCE_WHITE_NITS}", "format=gbrpf32le", "zscale=p=bt709",
                  f"tonemap=tonemap=mobius:param=0.7:peak={peak:.3f}:desat=0",
                  "zscale=t=bt709:m=bt709:r=limited:dither=error_diffusion"]
    else:
        parts.append("zscale=t=bt709:p=bt709:m=bt709:r=limited:dither=error_diffusion")
    parts.append("format=yuv420p")
    return ",".join(parts)


BT709_TAGS = ["-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709", "-color_range", "tv"]
_DECODE_ERR = re.compile(r"error while decoding|corrupt|concealing \d+|Invalid NAL|missing picture|decode_slice_header error|"
                         r"Invalid data found|non-existing PPS|top block unavailable|left block unavailable", re.I)


def make_proxy(src: str | Path, dst: str | Path, height: int = 540, crf: int = 26, fps_cap: float = 30.0,
               src_fps: float | None = None, tech: dict[str, Any] | None = None) -> dict[str, Any]:
    """H.264 proxy with a 1 s GOP for instant seeking/scrubbing, faststart for streaming, converted to display
    SDR BT.709 (see display_filter). Returns how the colour was handled and how many decode errors were seen."""
    dst = Path(dst)
    tmp = dst.with_suffix(".tmp.mp4")
    gop = max(1, int(round(min(src_fps or fps_cap, fps_cap))))
    pre = f"fps={fps_cap}," if src_fps and src_fps > fps_cap + 0.5 else ""
    chains = []
    if tech:
        chains.append(("display", pre + display_filter(tech, height)))
    chains.append(("basic", pre + f"scale=-2:'min({height},ih)':flags=bicubic,format=yuv420p"))
    last: Exception | None = None
    for kind, vf in chains:
        args = [ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
                "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-g", str(gop), "-keyint_min", str(gop),
                "-sc_threshold", "0", *BT709_TAGS, "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart",
                "-map_metadata", "-1", str(tmp)]
        try:
            p = run(args)
        except RuntimeError as e:  # e.g. a colour description zimg cannot convert: fall back rather than fail
            last = e
            continue
        tmp.replace(dst)
        errs = sum(1 for line in p.stderr.decode(errors="replace").splitlines() if _DECODE_ERR.search(line))
        hdr = bool(tech and (tech.get("color_transfer") or "") in _HDR_TRC)
        return {"colour": ("hdr_tonemapped" if hdr else "converted") if kind == "display" else "unconverted",
                "decode_errors": errs, "fallback_reason": str(last)[-300:] if last else None}
    raise last or RuntimeError("proxy failed")


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


def render_master(src: str | Path, dst_stem: str | Path, start: float, end: float, tech: dict[str, Any] | None = None) -> Path:
    """A trimmed copy of an original that keeps its quality for editing: 10-bit and 4:2:2 become ProRes 422 HQ,
    4:4:4 / RGB / alpha / 12-bit and up ProRes 4444 (10-bit, or 12-bit with alpha in ProRes itself), colour tags (HDR, log,
    BT.2020) and interlacing kept, PCM audio. Plain 8-bit 4:2:0 stays H.264 at near-transparent quality. Returns the file."""
    tech = tech or technical_metadata(src)
    pix = tech.get("pix_fmt") or ""
    depth = int(tech.get("bit_depth") or 8)
    alpha = pix.startswith(("yuva", "gbrap", "rgba", "bgra", "argb", "abgr", "ya"))
    rich = depth > 8 or (tech.get("chroma") in ("4:2:2", "4:4:4")) or alpha or _is_rgb(pix) or bool(tech.get("hdr"))
    dur = max(0.04, end - start)
    tags = []
    for opt, key in (("-colorspace", "color_space"), ("-color_trc", "color_transfer"), ("-color_primaries", "color_primaries"),
                     ("-color_range", "color_range")):
        if tech.get(key) and tech[key] not in ("unknown", "reserved"):
            tags += [opt, str(tech[key])]
    vf = ["-vf", "setfield=tff"] if tech.get("interlaced") else []
    il = ["-flags", "+ildct+ilme"] if tech.get("interlaced") else []
    if rich:
        four = tech.get("chroma") == "4:4:4" or alpha or _is_rgb(pix) or depth > 10
        dst = Path(dst_stem).with_suffix(".mov")
        venc = ["-c:v", "prores_ks", "-profile:v", "4" if four else "3", "-vendor", "apl0",
                "-pix_fmt", ("yuva444p10le" if alpha else "yuv444p10le") if four else "yuv422p10le", *il]
        aenc = ["-c:a", "pcm_s24le"]
    else:
        dst = Path(dst_stem).with_suffix(".mp4")
        venc = ["-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", *il]
        aenc = ["-c:a", "aac", "-b:a", "256k"]
    run([ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}", "-map", "0:v:0", "-map", "0:a?",
         *vf, *venc, *tags, *aenc, "-map_metadata", "0", "-movflags", "+faststart", str(dst)])
    return dst


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
