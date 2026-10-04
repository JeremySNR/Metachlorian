"""Deterministic image-quality and look measurements on keyframes."""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def _gray(rgb: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian normalised by local contrast, resolution-independent (0..~1)."""
    import cv2

    g = cv2.resize(gray, (640, int(640 * gray.shape[0] / gray.shape[1]))) if gray.shape[1] != 640 else gray
    lap = cv2.Laplacian(g.astype(np.float32), cv2.CV_32F, ksize=3)
    contrast = float(g.std()) + 8.0
    return float(min(1.0, math.sqrt(lap.var()) / contrast / 2.2))


def noise_sigma(gray: np.ndarray) -> float:
    """Immerkær's fast noise variance estimate (sigma in 8-bit levels)."""
    import cv2

    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    g = gray.astype(np.float32)
    conv = cv2.filter2D(g, -1, k)
    h, w = g.shape
    return float(np.abs(conv[1:-1, 1:-1]).sum() * math.sqrt(0.5 * math.pi) / (6 * (w - 2) * (h - 2)))


def blockiness(gray: np.ndarray) -> float:
    """Ratio of luminance discontinuity on 8-px block edges vs elsewhere (1.0 = none)."""
    g = gray.astype(np.float32)
    dx = np.abs(np.diff(g, axis=1))
    if dx.shape[1] < 16:
        return 1.0
    edge = dx[:, 7::8].mean()
    other = np.delete(dx, np.s_[7::8], axis=1).mean() + 1e-3
    return float(edge / other)


def exposure(gray: np.ndarray) -> dict[str, float]:
    total = gray.size
    return {"mean": float(gray.mean() / 255.0), "clipped_high": float((gray >= 250).sum() / total),
            "crushed_low": float((gray <= 5).sum() / total), "p2": float(np.percentile(gray, 2) / 255.0),
            "p98": float(np.percentile(gray, 98) / 255.0)}


def colourfulness(rgb: np.ndarray) -> float:
    """Hasler & Süsstrunk colourfulness metric."""
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    rg = r - g
    yb = 0.5 * (r + g) - b
    return float(math.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2))


def saturation(rgb: np.ndarray) -> float:
    import cv2

    return float(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 1].mean() / 255.0)


def dominant_colours(rgb: np.ndarray, k: int = 5) -> list[dict[str, Any]]:
    import cv2

    small = cv2.resize(rgb, (64, 36), interpolation=cv2.INTER_AREA).reshape(-1, 3).astype(np.float32)
    lab = cv2.cvtColor(small.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centres = cv2.kmeans(lab, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k) / len(labels)
    rgbc = cv2.cvtColor(centres.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2RGB).reshape(-1, 3)
    order = np.argsort(-counts)
    return [{"hex": "#%02x%02x%02x" % tuple(int(x) for x in rgbc[i]), "share": round(float(counts[i]), 3)} for i in order]


def letterbox(gray: np.ndarray) -> dict[str, float]:
    """Black bars: fraction of height/width that is uniformly dark at the edges."""
    rows = gray.mean(axis=1)
    cols = gray.mean(axis=0)

    def run(v: np.ndarray) -> int:
        n = 0
        for x in v:
            if x < 12:
                n += 1
            else:
                break
        return n

    h, w = gray.shape
    top, bottom = run(rows), run(rows[::-1])
    left, right = run(cols), run(cols[::-1])
    return {"bars_vertical": round((top + bottom) / h, 3) if top > 2 and bottom > 2 else 0.0,
            "bars_horizontal": round((left + right) / w, 3) if left > 2 and right > 2 else 0.0}


def saliency_centre(rgb: np.ndarray) -> tuple[float, float]:
    """Spectral-residual saliency (Hou & Zhang 2007) centroid, as fractions of width/height."""
    import cv2

    g = cv2.resize(_gray(rgb), (128, 72)).astype(np.float32)
    f = np.fft.fft2(g)
    log_amp = np.log(np.abs(f) + 1e-6)
    phase = np.angle(f)
    resid = log_amp - cv2.blur(log_amp, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(resid + 1j * phase))) ** 2
    sal = cv2.GaussianBlur(sal, (9, 9), 2.5)
    sal = sal / (sal.sum() + 1e-9)
    ys, xs = np.mgrid[0:72, 0:128]
    return float((sal * xs).sum() / 128), float((sal * ys).sum() / 72)


def measure(rgb: np.ndarray) -> dict[str, Any]:
    g = _gray(rgb)
    ex = exposure(g)
    contrast = ex["p98"] - ex["p2"]
    sat = saturation(rgb)
    cx, cy = saliency_centre(rgb)
    return {"sharpness": round(sharpness(g), 4), "noise": round(noise_sigma(g), 3), "blockiness": round(blockiness(g), 3),
            "exposure": {k: round(v, 4) for k, v in ex.items()}, "contrast": round(contrast, 4), "saturation": round(sat, 4),
            "colourfulness": round(colourfulness(rgb), 2), "letterbox": letterbox(g), "saliency": [round(cx, 3), round(cy, 3)]}


def log_likeness(ms: list[dict[str, Any]]) -> float:
    """How much the frames look like an ungraded log/flat profile: raised blacks,
    compressed highlights, low saturation and contrast, no clipping. 0..1."""
    if not ms:
        return 0.0
    p2 = np.median([m["exposure"]["p2"] for m in ms])
    p98 = np.median([m["exposure"]["p98"] for m in ms])
    sat = np.median([m["saturation"] for m in ms])
    clip = np.median([m["exposure"]["clipped_high"] + m["exposure"]["crushed_low"] for m in ms])
    score = 0.0
    score += np.clip((p2 - 0.04) / 0.08, 0, 1) * 0.3
    score += np.clip((0.88 - p98) / 0.12, 0, 1) * 0.25
    score += np.clip((0.28 - sat) / 0.15, 0, 1) * 0.3
    score += np.clip((0.01 - clip) / 0.01, 0, 1) * 0.15
    return float(round(score, 3))


def flags(m: dict[str, Any], stability: float | None = None) -> list[str]:
    out = []
    ex = m["exposure"]
    if m["sharpness"] < 0.12:
        out.append("out_of_focus")
    if ex["mean"] < 0.12 and ex["crushed_low"] > 0.3:
        out.append("underexposed")
    if ex["clipped_high"] > 0.2:
        out.append("overexposed")
    if m["noise"] > 6.0:
        out.append("noise")
    if m["blockiness"] > 1.6:
        out.append("compression_artefacts")
    if m["letterbox"]["bars_vertical"] > 0.05 or m["letterbox"]["bars_horizontal"] > 0.05:
        out.append("letterbox_pillarbox")
    if stability is not None and stability < 0.25:
        out.append("camera_shake")
    return out
