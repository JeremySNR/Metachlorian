from __future__ import annotations

from typing import Any

import numpy as np

from ..media import ffmpeg
from .base import AnalysisContext, Analyser


def sample_times(start: float, end: float, max_frames: int = 5, every_s: float = 3.0) -> list[float]:
    """Keyframe times for a shot: one per ``every_s`` seconds, at least one, at most
    ``max_frames``, kept away from the boundaries (dissolve frames, motion blur at cuts)."""
    dur = max(0.0, end - start)
    if dur < 0.5:
        return [start + dur / 2]
    n = int(min(max_frames, max(1, round(dur / every_s) + (1 if dur > 2 else 0))))
    if n == 1:
        return [start + dur / 2]
    lo, hi = start + 0.12 * dur, end - 0.12 * dur
    return [float(x) for x in np.linspace(lo, hi, n)]


class KeyframeAnalyser(Analyser):
    name = "keyframes"
    version = "1.0.0"
    requires = ("shots",)
    priority = 85
    description = ("Representative keyframes per shot (one per ~3 s, up to 5, avoiding transition frames) and a poster "
                   "thumbnail. These feed every image analyser so frames are decoded once.")

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        import cv2

        kdir = ctx.work_dir / "kf"
        kdir.mkdir(exist_ok=True)
        for old in kdir.glob("*.jpg"):
            old.unlink()
        src = ctx.proxy_path
        total = 0
        for shot in ctx.shots():
            times = sample_times(shot.start_s, shot.end_s)
            frames = []
            kfs = []
            for i, t in enumerate(times):
                try:
                    rgb = ffmpeg.frame_at(src, t)
                except RuntimeError:
                    continue
                name = f"{shot.idx:05d}_{i}.jpg"
                ffmpeg.save_jpeg(rgb, kdir / name, 88)
                gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                sharp = float(cv2.Laplacian(gray, cv2.CV_32F).var())
                frames.append((sharp, i))
                kfs.append({"t": round(t, 3), "file": f"kf/{name}", "w": int(rgb.shape[1]), "h": int(rgb.shape[0])})
            if not kfs:
                continue
            # Poster: the sharpest of the middle frames (skip the ends when there are 3+).
            pool = frames[1:-1] if len(frames) >= 3 else frames
            best = max(pool)[1]
            for k in kfs:
                k["poster"] = False
            poster = next(k for k in kfs if k["file"].endswith(f"_{best}.jpg"))
            poster["poster"] = True
            thumb = ctx.work_dir / "kf" / f"{shot.idx:05d}_thumb.jpg"
            img = cv2.cvtColor(cv2.imread(str(ctx.work_dir / poster["file"])), cv2.COLOR_BGR2RGB)
            ffmpeg.save_jpeg(img, thumb, 80, width=384)
            ctx.keyframe_updates[shot.id] = kfs
            total += len(kfs)
        return {"keyframes": total}
