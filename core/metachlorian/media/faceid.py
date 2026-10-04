"""Face identity: YuNet detection with landmarks, SFace alignment and 128-d embeddings (both from the
OpenCV model zoo, CPU). Everything stays on this machine."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

MIN_FACE_PX = 40      # smaller faces give unreliable embeddings
MIN_SCORE = 0.8
MAX_YAW = 0.3         # |nose offset from the eye midpoint| / eye distance; turned faces embed unreliably


class FaceID:
    def __init__(self, yunet: Path, sface: Path):
        import cv2

        self.det = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), MIN_SCORE, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(str(sface), "")

    def faces(self, rgb: np.ndarray, min_px: int = MIN_FACE_PX) -> list[dict[str, Any]]:
        """Faces large enough to recognise: normalised box, detector score, size, unit embedding, aligned crop (BGR 112x112)."""
        import cv2

        H, W = rgb.shape[:2]
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        scale = 1.0 if max(W, H) <= 1280 else 1280 / max(W, H)
        img = cv2.resize(bgr, (int(W * scale), int(H * scale))) if scale != 1 else bgr
        self.det.setInputSize((img.shape[1], img.shape[0]))
        _, rows = self.det.detect(img)
        out = []
        for f in rows if rows is not None else []:
            row = f.copy()
            row[:14] = row[:14] / scale  # box and five landmarks back to full resolution
            x, y, w, h = (float(v) for v in row[:4])
            if min(w, h) < min_px:
                continue
            (rx, ry), (lx, ly), (nx, ny) = row[4:6], row[6:8], row[8:10]
            eye = float(np.hypot(lx - rx, ly - ry))
            if eye < 0.2 * w:
                continue  # profile or badly foreshortened
            # Yaw: the nose's offset from the eye midpoint, measured along the eye line.
            ux, uy = (lx - rx) / eye, (ly - ry) / eye
            yaw = ((nx - (rx + lx) / 2) * ux + (ny - (ry + ly) / 2) * uy) / eye
            if abs(yaw) > MAX_YAW:
                continue
            crop = self.rec.alignCrop(bgr, row)
            feat = self.rec.feature(crop).reshape(-1).astype(np.float32)
            feat /= np.linalg.norm(feat) + 1e-9
            out.append({"box": [round(max(0.0, x) / W, 4), round(max(0.0, y) / H, 4), round(min(W, x + w) / W, 4), round(min(H, y + h) / H, 4)],
                        "score": round(float(row[14]), 3), "size_px": int(min(w, h)), "embedding": feat, "crop": crop})
        return out


@lru_cache(maxsize=2)
def load(yunet: str, sface: str) -> FaceID:
    return FaceID(Path(yunet), Path(sface))


def iou(a: list[float], b: list[float]) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
