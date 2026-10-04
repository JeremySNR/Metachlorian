"""Deterministic camera-motion estimation.

Sparse KLT feature tracking between frames sampled at ``fps``, a RANSAC
similarity fit per step (translation, scale, rotation) for the global camera
motion, and the residuals for parallax (dolly/truck vs pan/zoom) and subject
motion. Shot-level statistics are then classified into controlled-vocabulary
camera movements with a confidence derived from the margin to the threshold.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import ffmpeg

MW, MH = 320, 180


@dataclass
class Thresholds:
    pan: float = 0.045        # fraction of frame width per second
    tilt: float = 0.04
    zoom: float = 0.035       # log-scale per second
    roll: float = 2.0         # degrees per second
    jitter_handheld: float = 0.0035   # high-frequency translation, fraction of width per step
    jitter_static: float = 0.0012
    parallax: float = 0.55    # px residual (at 320 px) above which motion has depth
    whip: float = 0.9         # fraction of width per second


def track_steps(frames: list[np.ndarray]) -> list[dict[str, float]]:
    import cv2

    steps = []
    prev = frames[0]
    cy, cx = prev.shape[0] / 2.0, prev.shape[1] / 2.0
    for cur in frames[1:]:
        pts = cv2.goodFeaturesToTrack(prev, maxCorners=400, qualityLevel=0.01, minDistance=7, blockSize=7)
        rec = {"n": 0, "tx": 0.0, "ty": 0.0, "s": 1.0, "r": 0.0, "inl": 0.0, "par": 0.0, "obj": 0.0, "mag": 0.0, "ok": 0.0}
        if pts is not None and len(pts) >= 12:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, winSize=(21, 21), maxLevel=3,
                                                 criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03))
            good = st.ravel() == 1
            p0, p1 = pts[good].reshape(-1, 2), nxt[good].reshape(-1, 2)
            if len(p0) >= 10:
                M, inl = cv2.estimateAffinePartial2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=1.5, maxIters=2000, confidence=0.99)
                if M is not None:
                    a, b = M[0, 0], M[1, 0]
                    pred = p0 @ M[:, :2].T + M[:, 2]
                    res = np.linalg.norm(p1 - pred, axis=1)
                    inl = inl.ravel().astype(bool)
                    flow = np.linalg.norm(p1 - p0, axis=1)
                    # Parallax: residual structure among near-inliers (depth-dependent motion).
                    near = res < 6.0
                    rec.update({
                        # Translation of the frame centre, so zooming about the centre is not read as a pan.
                        "n": int(len(p0)), "tx": float(a * cx - b * cy + M[0, 2] - cx), "ty": float(b * cx + a * cy + M[1, 2] - cy),
                        "s": float(math.hypot(a, b)),
                        "r": float(math.degrees(math.atan2(b, a))), "inl": float(inl.mean()),
                        "par": float(np.median(res[near])) if near.any() else 0.0,
                        "obj": float(np.mean(res > 3.0)), "mag": float(np.mean(flow)), "ok": 1.0,
                    })
        steps.append(rec)
        prev = cur
    return steps


def shot_frames(path: str | Path, start: float, end: float, fps: float) -> list[np.ndarray]:
    dur = max(0.0, end - start)
    return list(ffmpeg.iter_frames(path, MW, MH, fps=fps, gray=True, start=start, duration=dur))


def summarise(steps: list[dict[str, float]], fps: float, th: Thresholds | None = None) -> dict[str, Any]:
    th = th or Thresholds()
    ok = [s for s in steps if s["ok"]]
    if len(ok) < 2:
        return {"valid": False, "movements": [], "stats": {"steps": len(steps), "tracked": len(ok)}}
    tx = np.array([s["tx"] for s in ok]) / MW
    ty = np.array([s["ty"] for s in ok]) / MW
    ls = np.log(np.array([s["s"] for s in ok]))
    rot = np.array([s["r"] for s in ok])
    par = float(np.median([s["par"] for s in ok]))
    obj = float(np.mean([s["obj"] for s in ok]))
    mag = float(np.mean([s["mag"] for s in ok])) / MW * fps

    def smooth(x: np.ndarray, w: int) -> np.ndarray:
        if len(x) < w:
            return np.full_like(x, x.mean())
        k = np.ones(w) / w
        return np.convolve(np.pad(x, (w // 2, w - 1 - w // 2), mode="edge"), k, mode="valid")

    w = max(3, int(round(fps * 0.8)))
    jitter = float(np.sqrt(np.mean((tx - smooth(tx, w)) ** 2 + (ty - smooth(ty, w)) ** 2)))
    vx, vy = float(tx.mean() * fps), float(ty.mean() * fps)
    vz, vr = float(ls.mean() * fps), float(rot.mean() * fps)
    peak_vx = float(np.max(np.abs(smooth(tx, max(2, w // 2)))) * fps)
    consist_x = float(np.mean(np.sign(tx) == np.sign(vx))) if abs(vx) > 1e-6 else 0.0
    consist_y = float(np.mean(np.sign(ty) == np.sign(vy))) if abs(vy) > 1e-6 else 0.0
    consist_z = float(np.mean(np.sign(ls) == np.sign(vz))) if abs(vz) > 1e-9 else 0.0
    tracked = float(np.mean([s["n"] for s in ok]))

    moves: list[tuple[str, float]] = []

    def conf(value: float, thr: float, consistency: float = 1.0) -> float:
        return float(min(0.99, max(0.05, (1 - math.exp(-2.0 * (abs(value) / thr - 1) - 0.4)) * (0.5 + 0.5 * consistency))))

    deep = par > th.parallax
    if peak_vx > th.whip and len(ok) < fps * 3:
        moves.append(("whip_pan", conf(peak_vx, th.whip)))
    if abs(vx) > th.pan and consist_x > 0.55:
        # Content moving left (vx < 0) means the camera turns/travels right.
        right = vx < 0
        if deep:
            moves.append(("truck_right" if right else "truck_left", conf(vx, th.pan, consist_x) * 0.8))
            moves.append(("tracking", conf(vx, th.pan, consist_x) * 0.6))
        else:
            moves.append(("pan_right" if right else "pan_left", conf(vx, th.pan, consist_x)))
    if abs(vy) > th.tilt and consist_y > 0.55:
        up = vy > 0  # content moving down => camera tilts up
        if deep:
            moves.append(("pedestal", conf(vy, th.tilt, consist_y) * 0.6))
        else:
            moves.append(("tilt_up" if up else "tilt_down", conf(vy, th.tilt, consist_y)))
    if abs(vz) > th.zoom and consist_z > 0.55:
        inward = vz > 0
        if deep:
            moves.append(("push_in" if inward else "pull_out", conf(vz, th.zoom, consist_z) * 0.85))
        else:
            moves.append(("zoom_in" if inward else "zoom_out", conf(vz, th.zoom, consist_z) * 0.85))
    if abs(vr) > th.roll:
        moves.append(("roll", conf(vr, th.roll)))
    moving = bool(moves)
    if jitter > th.jitter_handheld:
        moves.append(("handheld", conf(jitter, th.jitter_handheld)))
    elif moving and jitter < th.jitter_handheld * 0.6 and (deep or abs(vx) > th.pan):
        # Smooth, stabilised movement through space.
        moves.append(("gimbal", 0.35 + 0.3 * (1 - jitter / th.jitter_handheld)))
    if not moving and jitter <= th.jitter_static:
        moves.append(("static", float(min(0.99, 0.6 + 0.4 * (1 - jitter / th.jitter_static)))))
    elif not moving and jitter <= th.jitter_handheld:
        # Slight drift without clear movement: locked-off-ish, low confidence.
        moves.append(("static", 0.45))
    return {
        "valid": True,
        "movements": [{"term": m, "confidence": round(c, 3)} for m, c in moves],
        "stats": {"vx": round(vx, 4), "vy": round(vy, 4), "zoom": round(vz, 4), "roll_dps": round(vr, 3),
                  "jitter": round(jitter, 5), "parallax_px": round(par, 3), "subject_motion": round(obj, 3),
                  "flow": round(mag, 4), "tracked_points": round(tracked, 1), "steps": len(steps)},
        "motion_energy": round(min(1.0, mag * 2.5 + obj * 0.5), 4),
        "stability": round(float(max(0.0, 1.0 - jitter / (th.jitter_handheld * 3))), 3),
    }


def analyse_shot(path: str | Path, start: float, end: float, fps: float = 15.0, th: Thresholds | None = None) -> dict[str, Any]:
    dur = end - start
    sample_fps = fps if dur <= 30 else max(5.0, fps * 30 / dur)
    frames = shot_frames(path, start, end, sample_fps)
    if len(frames) < 3:
        return {"valid": False, "movements": [], "stats": {"steps": 0}}
    return summarise(track_steps(frames), sample_fps, th)
