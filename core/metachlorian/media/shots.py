"""Shot boundary detection: hard cuts, dissolves and fades, plus splitting of
long single takes into meaningful segments. Deterministic and CPU-only.

The detector works on tiny frames (96x54) decoded from the proxy:

* Hard cuts: a frame-to-frame distance (colour histogram + pixel difference)
  that stands out from its neighbourhood (adaptive ratio test), with a flash
  check (t-1 vs t+1 similar => flash, not a cut).
* Dissolves: a large distance between frames k apart whose midpoint is close to
  the linear blend of the two ends, with no single dominant spike inside.
* Fades: runs of near-uniform black or white frames between content.
* Long takes: split where the content has drifted far from the segment start,
  or at the calmest moment once a segment exceeds the maximum length.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import ffmpeg

W, H = 96, 54


@dataclass
class Params:
    cut_ratio: float = 3.0         # score must exceed this multiple of the local mean
    cut_min: float = 0.20          # ... and this absolute floor
    cut_window: int = 8            # frames each side for the local mean
    flash_sim: float = 0.10        # t-1 vs t+1 distance below this => flash
    min_shot_s: float = 0.35
    dissolve_span_s: float = 0.4   # half-span k for the dissolve test
    dissolve_min: float = 0.40
    dissolve_blend_max: float = 0.55
    dark_luma: float = 0.07
    dark_std: float = 0.035
    max_segment_s: float = 20.0
    drift_split: float = 0.42
    min_segment_s: float = 4.0


@dataclass
class Boundary:
    frame: int          # first frame of the new shot (proxy frame index)
    kind: str           # cut | dissolve | fade
    score: float
    span: tuple[int, int] = (0, 0)


@dataclass
class Features:
    fps: float
    hist: np.ndarray        # (n, 64) normalised histograms
    small: np.ndarray       # (n, 27, 48) float32 grey
    luma: np.ndarray        # (n,)
    luma_std: np.ndarray    # (n,)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.luma)


def _hist(rgb: np.ndarray) -> np.ndarray:
    import cv2

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h = cv2.calcHist([hsv], [0], None, [32], [0, 180]).ravel()
    s = cv2.calcHist([hsv], [1], None, [16], [0, 256]).ravel()
    v = cv2.calcHist([hsv], [2], None, [16], [0, 256]).ravel()
    out = np.concatenate([h, s, v]).astype(np.float32)
    return out / (out.sum() / 3.0 + 1e-6)


def extract_features(path: str | Path, fps: float | None = None) -> Features:
    import cv2

    hists, smalls, lumas, stds = [], [], [], []
    for rgb in ffmpeg.iter_frames(path, W, H):
        hists.append(_hist(rgb))
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        sm = cv2.resize(g, (48, 27), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        smalls.append(sm)
        lumas.append(float(sm.mean()))
        stds.append(float(sm.std()))
    if fps is None:
        info = ffmpeg.ffprobe(path)
        v = next(s for s in info["streams"] if s.get("codec_type") == "video")
        fps = ffmpeg._ratio(v.get("avg_frame_rate")) or 25.0
    if not hists:
        return Features(fps, np.zeros((0, 64), np.float32), np.zeros((0, 27, 48), np.float32), np.zeros(0), np.zeros(0))
    return Features(fps, np.stack(hists), np.stack(smalls), np.array(lumas), np.array(stds))


def _dist(f: Features, a: np.ndarray | int, b: np.ndarray | int) -> np.ndarray:
    hd = 0.5 * np.abs(f.hist[a] - f.hist[b]).sum(axis=-1) / 3.0
    pd = np.abs(f.small[a] - f.small[b]).mean(axis=(-1, -2))
    return 0.55 * hd + 0.45 * np.minimum(1.0, pd * 4.0)


def _is_flash(f: Features, t: int, p: Params, local: float) -> bool:
    """A one- or two-frame event: the content after it matches the content before it."""
    thr = p.flash_sim * (1 + 2 * local) + 0.05
    for before, after in ((t - 1, t + 1), (t - 2, t), (t - 1, t + 2), (t - 3, t + 1)):
        if 0 <= before and after < f.n and before < t <= after and float(_dist(f, before, after)) < thr:
            return True
    return False


def detect(f: Features, p: Params | None = None) -> list[Boundary]:
    p = p or Params()
    n = f.n
    if n < 3:
        return []
    idx = np.arange(1, n)
    s = np.concatenate([[0.0], _dist(f, idx - 1, idx)])  # s[t] = d(t-1, t)
    dark = (f.luma < p.dark_luma) & (f.luma_std < p.dark_std)
    bright = (f.luma > 0.93) & (f.luma_std < p.dark_std)
    blank = dark | bright
    min_len = max(2, int(round(p.min_shot_s * f.fps)))
    out: list[Boundary] = []

    # ---- hard cuts
    w = p.cut_window
    for t in range(1, n):
        if blank[t] or blank[t - 1]:
            continue
        lo, hi = max(1, t - w), min(n, t + w + 1)
        neigh = np.concatenate([s[lo:t], s[t + 1:hi]])
        local = float(np.mean(neigh)) if len(neigh) else 0.0
        if s[t] < p.cut_min or s[t] < p.cut_ratio * local + 0.02:
            continue
        if not (s[t] >= s[max(1, t - 1)] and s[t] >= s[min(n - 1, t + 1)]):
            continue
        # Flash / single-frame glitch: the frame after looks like the frame before.
        if _is_flash(f, t, p, local):
            continue
        out.append(Boundary(t, "cut", float(s[t]), (t, t)))

    # ---- fades through black/white
    t = 0
    while t < n:
        if blank[t]:
            start = t
            while t < n and blank[t]:
                t += 1
            end = t  # exclusive
            if end - start <= 2 and start > 0 and end < n and float(_dist(f, start - 1, end)) < 0.25:
                continue  # a flash or a dropped frame, not a fade
            if start == 0 or end >= n:
                # Leading/trailing black: boundary where content starts/ends.
                b = end if start == 0 else start
                if 0 < b < n and (end - start) >= min_len:
                    out.append(Boundary(b, "fade", 1.0, (start, end)))
                continue
            # Extend through the ramps either side.
            a0 = start
            while a0 > 1 and f.luma[a0 - 1] > f.luma[a0] + 0.003 and (start - a0) < 2 * f.fps:
                a0 -= 1
            b0 = end
            while b0 < n - 1 and f.luma[b0] > f.luma[b0 - 1] + 0.003 and (b0 - end) < 2 * f.fps:
                b0 += 1
            if (end - start) > 1.5 * f.fps:
                out.append(Boundary(start, "fade", 1.0, (a0, start)))
                out.append(Boundary(end, "fade", 1.0, (end, b0)))
            else:
                out.append(Boundary((start + end) // 2, "fade", 1.0, (a0, b0)))
        else:
            t += 1

    # ---- dissolves
    k = max(3, int(round(p.dissolve_span_s * f.fps)))
    if n > 2 * k + 2:
        ts = np.arange(k, n - k)
        dk = _dist(f, ts - k, ts + k)
        blend = np.abs(f.small[ts] - 0.5 * (f.small[ts - k] + f.small[ts + k])).mean(axis=(1, 2))
        ends = np.abs(f.small[ts - k] - f.small[ts + k]).mean(axis=(1, 2)) + 1e-4
        ratio = blend / ends
        for j in range(1, len(ts) - 1):
            t = int(ts[j])
            if dk[j] < p.dissolve_min or dk[j] < dk[j - 1] or dk[j] < dk[j + 1]:
                continue
            inner = s[t - k + 1: t + k + 1]
            if inner.max() > 0.6 * dk[j] or inner.max() > p.cut_min * 1.6 and inner.max() > 3 * np.median(inner):
                continue  # a hard cut explains it
            if ratio[j] > p.dissolve_blend_max:
                continue  # not a blend: camera or subject motion
            # Motion check: during a dissolve both end frames stay visible; consecutive
            # differences are small and even.
            if np.std(inner) > 0.5 * np.mean(inner) + 0.01 and np.mean(inner) > 0.03:
                continue
            if blank[t - k: t + k + 1].any():
                continue
            out.append(Boundary(t, "dissolve", float(dk[j]), (t - k, t + k)))

    # ---- merge: keep the strongest boundary within min_len; prefer fade > dissolve > cut spans
    out.sort(key=lambda b: b.frame)
    merged: list[Boundary] = []
    for b in out:
        if merged and b.frame - merged[-1].frame < min_len:
            prev = merged[-1]
            rank = {"fade": 3, "cut": 2, "dissolve": 1}
            if (rank[b.kind], b.score) > (rank[prev.kind], prev.score):
                merged[-1] = b
            continue
        merged.append(b)
    return [b for b in merged if min_len <= b.frame <= n - 1]


def split_long(f: Features, start: int, end: int, p: Params) -> list[int]:
    """Split points inside a long single take [start, end)."""
    fps = f.fps
    if (end - start) / fps <= p.max_segment_s:
        return []
    step = max(1, int(round(fps / 2)))
    min_seg = int(p.min_segment_s * fps)
    max_seg = int(p.max_segment_s * fps)
    splits: list[int] = []
    anchor = start
    t = start + min_seg
    motion = np.concatenate([[0.0], _dist(f, np.arange(start + 1, end) - 1, np.arange(start + 1, end))])
    while t < end - min_seg:
        drift = float(_dist(f, anchor, t))
        if drift > p.drift_split or t - anchor >= max_seg:
            if t - anchor >= max_seg and drift <= p.drift_split:
                # Forced split: choose the calmest frame in the last third.
                lo = anchor + int((t - anchor) * 0.66)
                window = motion[lo - start: t - start]
                t = lo + int(np.argmin(window)) if len(window) else t
            splits.append(t)
            anchor = t
            t = anchor + min_seg
            continue
        t += step
    return splits


def segment(path: str | Path, fps: float | None = None, p: Params | None = None, features: Features | None = None) -> tuple[list[dict[str, Any]], Features]:
    p = p or Params()
    f = features or extract_features(path, fps)
    bounds = detect(f, p)
    starts = [0] + [b.frame for b in bounds]
    kinds = ["cut"] + [b.kind for b in bounds]
    ends = starts[1:] + [f.n]
    shots: list[dict[str, Any]] = []
    for s0, e0, kind in zip(starts, ends, kinds):
        if e0 <= s0:
            continue
        parts = [s0, *split_long(f, s0, e0, p), e0]
        for i in range(len(parts) - 1):
            a, b = parts[i], parts[i + 1]
            shots.append({
                "start_s": a / f.fps, "end_s": b / f.fps, "proxy_start": a, "proxy_end": b,
                "kind": "segment" if len(parts) > 2 else "shot",
                "transition_in": kind if i == 0 else "continuous",
                "blank": bool(np.mean((f.luma[a:b] < p.dark_luma) & (f.luma_std[a:b] < p.dark_std)) > 0.8),
            })
    return shots, f


def pyscenedetect(path: str | Path, detector: str = "adaptive") -> list[float]:
    """Reference implementation for benchmarking (BSD-3 PySceneDetect)."""
    from scenedetect import AdaptiveDetector, ContentDetector, HistogramDetector, detect as sd_detect

    det = {"adaptive": AdaptiveDetector, "content": ContentDetector, "histogram": HistogramDetector}[detector]()
    scenes = sd_detect(str(path), det)
    return [s[0].get_seconds() for s in scenes[1:]]


def boundaries_seconds(shots: list[dict[str, Any]]) -> list[float]:
    return [s["start_s"] for s in shots[1:] if s["transition_in"] != "continuous"]


def frames_for(t: float, fps: float) -> int:
    return int(math.floor(t * fps + 1e-6))
