from __future__ import annotations

from typing import Any

import numpy as np

from .. import models
from ..media import siglip
from .base import AnalysisContext, Analyser


def load_keyframe(ctx: AnalysisContext, kf: dict[str, Any]) -> np.ndarray:
    import cv2

    img = cv2.imread(str(ctx.work_dir / kf["file"]))
    if img is None:
        raise FileNotFoundError(kf["file"])
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


class EmbedAnalyser(Analyser):
    name = "embed"
    version = "1.0.0"
    requires = ("keyframes",)
    priority = 80
    description = "SigLIP (multilingual, Apache-2.0) image embeddings per keyframe and per shot, for semantic and similarity search."

    def config(self, settings) -> dict[str, Any]:
        return {"model": "siglip-base-multilingual"}

    def check(self, settings) -> str | None:
        if not models.installed(settings.resolved_models_dir, "siglip-base-multilingual"):
            return "model 'siglip-base-multilingual' is not installed. Run: metachlorian models fetch siglip-base-multilingual"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        enc = siglip.load(str(ctx.models_dir))
        n = 0
        for shot in ctx.shots():
            if not shot.keyframes:
                continue
            imgs = [load_keyframe(ctx, kf) for kf in shot.keyframes]
            v = enc.encode_images(imgs)
            mean = v.mean(axis=0)
            mean /= np.linalg.norm(mean) + 1e-8
            ctx.vector(shot.id, "visual", mean)
            for row in v:
                ctx.vector(shot.id, "visual_kf", row)
            # Visual variety inside the shot: 1 - mean cosine to the shot centroid.
            ctx.shot_signal(shot, "pacing.visual_variety", round(float(1 - (v @ mean).mean()), 4), 1.0)
            n += len(imgs)
        return {"images": n, "dim": enc.dim}
