from __future__ import annotations

from typing import Any

import numpy as np

from ..media import quality as Q
from .base import AnalysisContext, Analyser
from .embed import load_keyframe


class QualityAnalyser(Analyser):
    name = "quality"
    version = "1.0.0"
    requires = ("keyframes",)
    priority = 65
    description = ("Sharpness, exposure, noise, compression artefacts, contrast, saturation, dominant colours, letterboxing, "
                   "log/flat-profile likeness and subject position. Deterministic image measurements.")

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        all_ms = []
        flagged = 0
        for shot in ctx.shots():
            if not shot.keyframes:
                continue
            ms = [Q.measure(load_keyframe(ctx, kf)) for kf in shot.keyframes]
            all_ms.extend(ms)
            agg = {
                "sharpness": round(float(np.median([m["sharpness"] for m in ms])), 4),
                "noise": round(float(np.median([m["noise"] for m in ms])), 3),
                "blockiness": round(float(np.median([m["blockiness"] for m in ms])), 3),
                "exposure": round(float(np.median([m["exposure"]["mean"] for m in ms])), 4),
                "clipped_high": round(float(np.median([m["exposure"]["clipped_high"] for m in ms])), 4),
                "crushed_low": round(float(np.median([m["exposure"]["crushed_low"] for m in ms])), 4),
                "contrast": round(float(np.median([m["contrast"] for m in ms])), 4),
                "saturation": round(float(np.median([m["saturation"] for m in ms])), 4),
                "colourfulness": round(float(np.median([m["colourfulness"] for m in ms])), 2),
            }
            mid = ms[len(ms) // 2]
            for k, v in agg.items():
                ctx.shot_signal(shot, f"quality.{k}", v, 1.0)
            ctx.shot_signal(shot, "look.dominant_colours", Q.dominant_colours(load_keyframe(ctx, shot.keyframes[len(ms) // 2])), 1.0)
            ctx.shot_signal(shot, "look.log_likeness", Q.log_likeness(ms), 1.0)
            ctx.shot_signal(shot, "look.letterbox", mid["letterbox"], 1.0)
            ctx.shot_signal(shot, "composition.saliency_centre", [round(float(np.mean([m["saliency"][0] for m in ms])), 3),
                                                                    round(float(np.mean([m["saliency"][1] for m in ms])), 3)], 0.6)
            fl = sorted({f for m in ms for f in Q.flags(m)})
            ctx.shot_signal(shot, "quality.flags_measured", fl, 1.0)
            flagged += bool(fl)
        asset_log = Q.log_likeness(all_ms)
        ctx.asset_signal("look.log_likeness", asset_log, 1.0)
        return {"shots_flagged": flagged, "log_likeness": asset_log}
