"""Face identity: one embedding per distinct face per shot, clustered into people a person can name.

Local only (YuNet + SFace on CPU); embeddings and face crops never leave this machine. Runs when
the ``face_identity`` setting is on (the default) and the SFace model is installed."""
from __future__ import annotations

from typing import Any

import numpy as np

from .. import models
from ..media import faceid
from .base import AnalysisContext, Analyser
from .embed import load_keyframe


class FacesAnalyser(Analyser):
    name = "faces"
    version = "1.0.0"
    requires = ("keyframes",)
    priority = 44
    resource = "cpu"
    description = "Recognises the same person across shots and files so people can be named and searched (local only)."

    def config(self, settings) -> dict[str, Any]:
        return {"min_px": faceid.MIN_FACE_PX, "min_score": faceid.MIN_SCORE, "max_yaw": faceid.MAX_YAW, "same_face": 0.55}

    def check(self, settings) -> str | None:
        if not settings.face_identity:
            return "face identity is switched off in Settings"
        root = settings.resolved_models_dir
        for m in ("yunet", "sface"):
            if not models.installed(root, m):
                return f"model '{m}' is not installed. Run: metachlorian models fetch {m}"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        import cv2

        root = ctx.models_dir
        fid = faceid.load(str(models.model_dir(root, "yunet") / "face_detection_yunet_2023mar.onnx"),
                          str(models.model_dir(root, "sface") / "face_recognition_sface_2021dec.onnx"))
        out_dir = ctx.work_dir / "faces"
        out_dir.mkdir(parents=True, exist_ok=True)
        for old in out_dir.glob("*.jpg"):
            old.unlink()
        faces: list[dict[str, Any]] = []
        for shot in ctx.shots():
            found: list[dict[str, Any]] = []
            for kf in shot.keyframes[:4]:
                for f in fid.faces(load_keyframe(ctx, kf)):
                    f["t"] = kf["t"]
                    # The same person seen on several keyframes of one shot is one face record.
                    same = next((g for g in found if float(g["embedding"] @ f["embedding"]) >= 0.55), None)
                    if same is None:
                        f["appearances"] = 1
                        found.append(f)
                    else:
                        same["appearances"] += 1
                        if f["size_px"] * f["score"] > same["size_px"] * same["score"]:
                            f["appearances"] = same["appearances"]
                            found[found.index(same)] = f
            for k, f in enumerate(found):
                name = f"faces/{shot.idx:05d}_{k}.jpg"
                cv2.imwrite(str(ctx.work_dir / name), f["crop"], [cv2.IMWRITE_JPEG_QUALITY, 88])
                faces.append({"shot_id": shot.id, "t": f["t"], "box": f["box"], "score": f["score"], "size_px": f["size_px"],
                              "appearances": f["appearances"], "thumb": name, "embedding": f["embedding"].astype(np.float32)})
            if found:
                ctx.shot_signal(shot, "people.recognisable_faces", len(found), 1.0)
        ctx.faces = faces
        return {"faces": len(faces), "shots_with_faces": len({f["shot_id"] for f in faces})}
