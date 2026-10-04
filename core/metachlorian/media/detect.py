"""Object and face detection with MediaPipe's Apache-2.0 TFLite models, run on
the LiteRT interpreter (no GPU/EGL libraries needed, works on headless NAS).

Raw anchor outputs are decoded here: EfficientDet-Lite (BiFPN levels 3-7,
3 scales x 3 aspect ratios) and BlazeFace short range (SSD anchors, 128 px).
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np

COCO90 = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light", "fire hydrant", "???",
          "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "???",
          "backpack", "umbrella", "???", "???", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
          "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "???", "wine glass", "cup", "fork",
          "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
          "chair", "couch", "potted plant", "bed", "???", "dining table", "???", "???", "toilet", "???", "tv", "laptop", "mouse",
          "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "???", "book", "clock", "vase",
          "scissors", "teddy bear", "hair drier", "toothbrush"]


def _interpreter(path: Path, threads: int = 2):
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:  # pragma: no cover - older installs
        from tflite_runtime.interpreter import Interpreter  # type: ignore
    it = Interpreter(model_path=str(path), num_threads=threads)
    it.allocate_tensors()
    return it


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float = 0.5) -> list[int]:
    order = np.argsort(-scores)
    keep: list[int] = []
    while len(order):
        i = order[0]
        keep.append(int(i))
        if len(order) == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0]); yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2]); yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        a = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        b = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        order = rest[inter / (a + b - inter + 1e-9) < iou]
    return keep


class ObjectDetector:
    def __init__(self, model: Path, threads: int = 2):
        self.it = _interpreter(model, threads)
        self.inp = self.it.get_input_details()[0]
        self.size = int(self.inp["shape"][1])
        outs = self.it.get_output_details()
        self.out_scores = next(o["index"] for o in outs if o["shape"][-1] != 4)
        self.out_boxes = next(o["index"] for o in outs if o["shape"][-1] == 4)
        self.anchors = self._anchors(self.size)

    @staticmethod
    def _anchors(size: int) -> np.ndarray:
        out = []
        for level in range(3, 8):
            stride = 2 ** level
            n = math.ceil(size / stride)
            for y in range(n):
                for x in range(n):
                    cy, cx = (y + 0.5) * stride, (x + 0.5) * stride
                    for octave in range(3):
                        for aspect in (1.0, 2.0, 0.5):
                            base = 4.0 * stride * 2 ** (octave / 3)
                            w = base * math.sqrt(aspect)
                            h = base / math.sqrt(aspect)
                            out.append((cy, cx, h, w))
        return np.array(out, np.float32)

    def detect(self, rgb: np.ndarray, threshold: float = 0.35, max_results: int = 50) -> list[dict]:
        import cv2

        H, W = rgb.shape[:2]
        x = cv2.resize(rgb, (self.size, self.size), interpolation=cv2.INTER_LINEAR).astype(np.float32)
        x = (x - 127.5) / 127.5
        self.it.set_tensor(self.inp["index"], x[None])
        self.it.invoke()
        logits = self.it.get_tensor(self.out_scores)[0]
        enc = self.it.get_tensor(self.out_boxes)[0]
        scores = logits if float(logits.min()) >= 0.0 and float(logits.max()) <= 1.0 else 1 / (1 + np.exp(-logits))
        best = scores.max(axis=1)
        cand = np.where(best >= threshold)[0]
        if not len(cand):
            return []
        a = self.anchors[cand]
        e = enc[cand]
        cy = e[:, 0] * a[:, 2] + a[:, 0]
        cx = e[:, 1] * a[:, 3] + a[:, 1]
        h = np.exp(e[:, 2]) * a[:, 2]
        w = np.exp(e[:, 3]) * a[:, 3]
        boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1) / self.size
        cls = scores[cand].argmax(axis=1)
        sc = best[cand]
        out = []
        for c in np.unique(cls):
            m = np.where(cls == c)[0]
            for k in nms(boxes[m], sc[m], 0.5):
                i = m[k]
                b = np.clip(boxes[i], 0, 1)
                out.append({"label": COCO90[int(c)] if c < len(COCO90) else str(c), "score": round(float(sc[i]), 3),
                            "box": [round(float(b[0]), 4), round(float(b[1]), 4), round(float(b[2]), 4), round(float(b[3]), 4)]})
        out.sort(key=lambda d: -d["score"])
        return [d for d in out if d["label"] != "???"][:max_results]


class FaceDetector:
    """BlazeFace short range: faces within ~2 m of the camera (close and medium shots)."""

    def __init__(self, model: Path, threads: int = 1):
        self.it = _interpreter(model, threads)
        self.inp = self.it.get_input_details()[0]
        outs = self.it.get_output_details()
        self.out_reg = next(o["index"] for o in outs if o["shape"][-1] == 16)
        self.out_cls = next(o["index"] for o in outs if o["shape"][-1] == 1)
        anchors = []
        for stride, per in ((8, 2), (16, 6)):
            n = 128 // stride
            for y in range(n):
                for x in range(n):
                    for _ in range(per):
                        anchors.append(((x + 0.5) / n, (y + 0.5) / n))
        self.anchors = np.array(anchors, np.float32)

    def _run(self, rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        import cv2

        x = cv2.resize(rgb, (128, 128), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 127.5 - 1.0
        self.it.set_tensor(self.inp["index"], x[None])
        self.it.invoke()
        return self.it.get_tensor(self.out_reg)[0], self.it.get_tensor(self.out_cls)[0, :, 0]

    def detect(self, rgb: np.ndarray, threshold: float = 0.6) -> list[dict]:
        """Runs on the full frame and on overlapping square tiles so small faces in
        wide frames are still found. Boxes are normalised [x0, y0, x1, y1]."""
        H, W = rgb.shape[:2]
        crops = [(0, 0, W, H)]
        side = min(W, H)
        if W > H * 1.2:
            for x0 in np.linspace(0, W - side, 3).astype(int):
                crops.append((int(x0), 0, side, side))
        elif H > W * 1.2:
            for y0 in np.linspace(0, H - side, 3).astype(int):
                crops.append((0, int(y0), side, side))
        boxes, scores = [], []
        for (x0, y0, cw, ch) in crops:
            reg, cls = self._run(rgb[y0:y0 + ch, x0:x0 + cw])
            sc = 1 / (1 + np.exp(-np.clip(cls, -80, 80)))
            for i in np.where(sc >= threshold)[0]:
                cx = reg[i, 0] / 128 + self.anchors[i, 0]
                cy = reg[i, 1] / 128 + self.anchors[i, 1]
                w, h = reg[i, 2] / 128, reg[i, 3] / 128
                bx = np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
                bx = bx * np.array([cw, ch, cw, ch]) + np.array([x0, y0, x0, y0])
                boxes.append(bx / np.array([W, H, W, H]))
                scores.append(float(sc[i]))
        if not boxes:
            return []
        B, S = np.array(boxes), np.array(scores)
        out = []
        for k in nms(B, S, 0.3):
            b = np.clip(B[k], 0, 1)
            if (b[2] - b[0]) < 0.01:
                continue
            out.append({"score": round(float(S[k]), 3), "box": [round(float(v), 4) for v in b]})
        return out


class YuNet:
    """OpenCV's YuNet face detector (MIT): small faces in wide frames, CPU-fast."""

    def __init__(self, model: Path):
        import cv2

        self.det = cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.6, 0.3, 5000)

    def detect(self, rgb: np.ndarray, threshold: float = 0.6) -> list[dict]:
        import cv2

        H, W = rgb.shape[:2]
        scale = 1.0 if max(W, H) <= 1280 else 1280 / max(W, H)
        img = cv2.cvtColor(cv2.resize(rgb, (int(W * scale), int(H * scale))) if scale != 1 else rgb, cv2.COLOR_RGB2BGR)
        self.det.setScoreThreshold(threshold)
        self.det.setInputSize((img.shape[1], img.shape[0]))
        _, faces = self.det.detect(img)
        out = []
        for f in faces if faces is not None else []:
            x, y, w, h = (float(v) / scale for v in f[:4])
            out.append({"score": round(float(f[14]), 3), "box": [round(max(0, x) / W, 4), round(max(0, y) / H, 4),
                                                                   round(min(W, x + w) / W, 4), round(min(H, y + h) / H, 4)]})
        return out


@lru_cache(maxsize=2)
def yunet(path: str) -> YuNet:
    return YuNet(Path(path))


@lru_cache(maxsize=2)
def object_detector(path: str) -> ObjectDetector:
    return ObjectDetector(Path(path))


@lru_cache(maxsize=2)
def face_detector(path: str) -> FaceDetector:
    return FaceDetector(Path(path))
