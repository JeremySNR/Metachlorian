from __future__ import annotations

from typing import Any

import numpy as np

from ..db import loads
from ..media import shots as S
from .base import AnalysisContext, Analyser


class ShotAnalyser(Analyser):
    name = "shots"
    version = "1.1.0"
    requires = ("proxy",)
    priority = 90
    description = ("Deterministic shot boundary detection (hard cuts, dissolves, fades) and splitting of long single takes "
                   "into segments. See docs/decisions/003-shot-segmentation.md for the benchmark.")

    def config(self, settings) -> dict[str, Any]:
        p = S.Params(max_segment_s=settings.max_segment_s)
        return p.__dict__

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        tech = loads(ctx.db.q1("SELECT tech FROM assets WHERE id=?", (ctx.asset["id"],))["tech"], {})
        src_fps = tech.get("fps") or 25.0
        info = S.ffmpeg.ffprobe(ctx.proxy_path)
        v = next(s for s in info["streams"] if s.get("codec_type") == "video")
        proxy_fps = S.ffmpeg._ratio(v.get("avg_frame_rate")) or src_fps
        shots, feats = S.segment(ctx.proxy_path, proxy_fps, S.Params(max_segment_s=ctx.settings.max_segment_s))
        duration = tech.get("duration") or (feats.n / proxy_fps)
        out = []
        for s in shots:
            start_s, end_s = float(s["start_s"]), float(min(s["end_s"], duration))
            out.append({**s, "start_s": start_s, "end_s": end_s,
                        "start_frame": int(round(start_s * src_fps)), "end_frame": int(round(end_s * src_fps))})
        if not out:
            out = [{"start_s": 0.0, "end_s": float(duration), "start_frame": 0, "end_frame": int(round(duration * src_fps)),
                    "kind": "shot", "transition_in": "cut", "blank": False}]
        ctx.new_shots = out
        # Visual change rate per shot (mean frame-to-frame distance per second), deterministic pacing input.
        idx = np.arange(1, feats.n)
        diffs = np.concatenate([[0.0], S._dist(feats, idx - 1, idx)]) if feats.n > 1 else np.zeros(feats.n)
        change = []
        for s in out:
            a, b = int(s["proxy_start"]), int(s["proxy_end"])
            seg = diffs[a + 1:b] if b - a > 1 else np.zeros(1)
            change.append(round(float(np.mean(seg)) if len(seg) else 0.0, 4))
        transitions = {k: sum(1 for s in out if s["transition_in"] == k) for k in ("cut", "dissolve", "fade", "continuous")}
        return {"shot_count": len(out), "segments": sum(1 for s in out if s["kind"] == "segment"), "transitions": transitions,
                "visual_change": change, "proxy_fps": proxy_fps, "blank_shots": [i for i, s in enumerate(out) if s.get("blank")]}
