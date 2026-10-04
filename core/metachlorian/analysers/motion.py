from __future__ import annotations

from typing import Any

from ..media import motion as M
from .base import AnalysisContext, Analyser


class MotionAnalyser(Analyser):
    name = "motion"
    version = "1.1.0"
    requires = ("shots",)
    priority = 60
    description = ("Camera movement (static, pan, tilt, zoom, dolly, truck, roll, handheld, gimbal), stability and motion "
                   "energy from optical-flow tracking. Deterministic; see docs/decisions/008-camera-motion.md.")

    def config(self, settings) -> dict[str, Any]:
        return {"fps": 15.0, "thresholds": M.Thresholds().__dict__}

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for shot in ctx.shots():
            r = M.analyse_shot(ctx.proxy_path, shot.start_s, shot.end_s)
            if not r.get("valid"):
                ctx.shot_signal(shot, "camera.motion_stats", r.get("stats", {}), 0.0)
                continue
            ctx.shot_signal(shot, "camera.movement", r["movements"], max((m["confidence"] for m in r["movements"]), default=0.0))
            ctx.shot_signal(shot, "camera.motion_stats", r["stats"], 1.0)
            ctx.shot_signal(shot, "pacing.motion_energy", r["motion_energy"], 1.0)
            ctx.shot_signal(shot, "quality.stability", r["stability"], 1.0)
            for m in r["movements"]:
                counts[m["term"]] = counts.get(m["term"], 0) + 1
        return {"movements": counts}
