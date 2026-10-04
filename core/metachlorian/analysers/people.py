"""People, faces and objects on keyframes. Counts and sizes only: no identity.

Face recognition (identity) is opt-in and not part of the default install
(see docs/privacy.md); this analyser never computes face embeddings.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .. import models
from ..media import detect
from .base import AnalysisContext, Analyser, Moment
from .embed import load_keyframe


def shot_size_from_people(faces: list[dict], persons: list[dict]) -> tuple[str | None, float]:
    """Deterministic shot-size estimate from the largest face/person height relative to the frame."""
    if faces:
        fh = max(f["box"][3] - f["box"][1] for f in faces)
        if fh > 0.55:
            return "extreme_close_up", 0.7
        if fh > 0.30:
            return "close_up", 0.7
        if fh > 0.17:
            return "medium_close_up", 0.6
        if fh > 0.09:
            return "medium_shot", 0.55
    if persons:
        ph = max(p["box"][3] - p["box"][1] for p in persons)
        top = min(p["box"][1] for p in persons if p["box"][3] - p["box"][1] == ph)
        cut_off = max(p["box"][3] for p in persons if p["box"][3] - p["box"][1] == ph) > 0.97
        if ph > 0.85 and cut_off:
            return "medium_shot", 0.45
        if ph > 0.6 and not cut_off:
            return "long_shot", 0.5
        if ph > 0.6:
            return "medium_long_shot", 0.4
        if ph > 0.25:
            return "long_shot", 0.45
        if ph < 0.12 and top > 0:
            return "extreme_wide_shot", 0.4
    return None, 0.0


class PeopleAnalyser(Analyser):
    name = "people"
    version = "1.0.0"
    requires = ("keyframes",)
    priority = 50
    resource = "model"
    description = "Person and face counts, face sizes and positions (no identity), COCO objects. MediaPipe models on LiteRT."

    def config(self, settings) -> dict[str, Any]:
        return {"objects": "efficientdet-lite2", "faces": "blazeface-short", "identity": False}

    def check(self, settings) -> str | None:
        root = settings.resolved_models_dir
        for m in ("efficientdet-lite2", "blazeface-short"):
            if not models.installed(root, m):
                return f"model '{m}' is not installed. Run: metachlorian models fetch {m}"
        try:
            import ai_edge_litert  # noqa: F401
        except ImportError:
            return "LiteRT is not installed: pip install ai-edge-litert"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        root = ctx.models_dir
        od = detect.object_detector(str(models.model_dir(root, "efficientdet-lite2") / "efficientdet_lite2.tflite"))
        fd = detect.face_detector(str(models.model_dir(root, "blazeface-short") / "blaze_face_short_range.tflite"))
        with_people = 0
        for shot in ctx.shots():
            if not shot.keyframes:
                continue
            per_kf = []
            for kf in shot.keyframes:
                rgb = load_keyframe(ctx, kf)
                objs = od.detect(rgb, 0.4)
                faces = fd.detect(rgb, 0.65)
                persons = [o for o in objs if o["label"] == "person"]
                per_kf.append({"t": kf["t"], "objects": objs, "faces": faces, "persons": persons})
            people_counts = [max(len(k["persons"]), len(k["faces"])) for k in per_kf]
            people = int(round(float(np.median(people_counts)))) if people_counts else 0
            peak = max(people_counts) if people_counts else 0
            faces_n = int(round(float(np.median([len(k["faces"]) for k in per_kf]))))
            label_counts: dict[str, list[float]] = {}
            for k in per_kf:
                for o in k["objects"]:
                    if o["label"] != "person":
                        label_counts.setdefault(o["label"], []).append(o["score"])
            objects = sorted(({"label": lbl, "confidence": round(float(np.mean(s)), 3), "frames": len(s)}
                              for lbl, s in label_counts.items() if len(s) >= max(1, len(per_kf) // 3)), key=lambda x: -x["confidence"])
            mid = per_kf[len(per_kf) // 2]
            size, size_conf = shot_size_from_people(mid["faces"], mid["persons"])
            # Faces near frame centre, large enough, consistently present => likely addressing camera.
            frontal = [f for k in per_kf for f in k["faces"]
                       if 0.25 < (f["box"][0] + f["box"][2]) / 2 < 0.75 and (f["box"][3] - f["box"][1]) > 0.12]
            face_presence = sum(1 for k in per_kf if k["faces"]) / len(per_kf)
            ctx.shot_signal(shot, "people.count", people, 0.75 if people else 0.6)
            ctx.shot_signal(shot, "people.peak_count", peak, 0.75)
            ctx.shot_signal(shot, "people.faces", faces_n, 0.8)
            ctx.shot_signal(shot, "people.face_presence", round(face_presence, 3), 0.8)
            ctx.shot_signal(shot, "people.centred_face", bool(frontal) and face_presence > 0.6, 0.6)
            ctx.shot_signal(shot, "content.objects_detected", objects, max((o["confidence"] for o in objects), default=0.0))
            ctx.shot_signal(shot, "people.boxes", [{"t": k["t"], "faces": [f["box"] for f in k["faces"]], "persons": [p["box"] for p in k["persons"]]}
                                                  for k in per_kf], 0.8)
            if size:
                ctx.shot_signal(shot, "camera.shot_size_measured", size, size_conf)
            if faces_n:
                ctx.moment(Moment(shot.id, "face", shot.start_s, shot.end_s, f"{faces_n} face{'s' if faces_n > 1 else ''}",
                                  {"count": faces_n}, 0.8))
            with_people += people > 0
        return {"shots_with_people": with_people}
