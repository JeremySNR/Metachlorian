"""SigLIP image/text encoder on ONNX Runtime (no PyTorch needed at runtime)."""
from __future__ import annotations

import json
import string
from functools import lru_cache
from pathlib import Path

import numpy as np

from .. import models

_PUNCT = str.maketrans("", "", string.punctuation)


class SigLIP:
    def __init__(self, model_dir: Path):
        import sentencepiece as spm

        self.dir = Path(model_dir)
        self.cfg = json.loads((self.dir / "config.json").read_text())
        self.size = int(self.cfg.get("image_size", 256))
        self.max_len = int(self.cfg.get("max_length", 64))
        self.dim = int(self.cfg.get("dim", 768))
        self.scale = float(np.exp(self.cfg["logit_scale"]))
        self.bias = float(self.cfg["logit_bias"])
        self.mean = np.array(self.cfg.get("mean", [0.5] * 3), np.float32)
        self.std = np.array(self.cfg.get("std", [0.5] * 3), np.float32)
        self.sp = spm.SentencePieceProcessor(model_file=str(self.dir / "spiece.model"))
        self._vision = None
        self._text = None

    @property
    def vision(self):
        if self._vision is None:
            self._vision = models.ort_session(self.dir / "vision.onnx")
        return self._vision

    @property
    def text(self):
        if self._text is None:
            name = "text.q.onnx" if (self.dir / "text.q.onnx").exists() else "text.onnx"
            self._text = models.ort_session(self.dir / name)
        return self._text

    def tokenize(self, s: str) -> list[int]:
        # Mirrors the Hugging Face SiglipTokenizer: lower-case, strip punctuation,
        # collapse whitespace, append </s> (id 1), pad with id 1.
        s = " ".join(s.lower().translate(_PUNCT).split())
        ids = self.sp.encode(s)[: self.max_len - 1] + [1]
        return ids + [1] * (self.max_len - len(ids))

    def preprocess(self, rgb: np.ndarray) -> np.ndarray:
        import cv2

        img = cv2.resize(rgb, (self.size, self.size), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        img = (img - self.mean) / self.std
        return img.transpose(2, 0, 1)

    def encode_images(self, images: list[np.ndarray], batch: int = 8) -> np.ndarray:
        out = []
        for i in range(0, len(images), batch):
            px = np.stack([self.preprocess(im) for im in images[i:i + batch]]).astype(np.float32)
            out.append(self.vision.run(None, {"pixel_values": px})[0])
        v = np.concatenate(out) if out else np.zeros((0, self.dim), np.float32)
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-8)

    def encode_texts(self, texts: list[str], batch: int = 16) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch):
            ids = np.array([self.tokenize(t) for t in texts[i:i + batch]], dtype=np.int64)
            out.append(self.text.run(None, {"input_ids": ids})[0])
        v = np.concatenate(out) if out else np.zeros((0, self.dim), np.float32)
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-8)

    def prob(self, img_vecs: np.ndarray, txt_vecs: np.ndarray) -> np.ndarray:
        """Sigmoid image-text match probability (SigLIP is trained with this head)."""
        return 1.0 / (1.0 + np.exp(-(img_vecs @ txt_vecs.T * self.scale + self.bias)))


@lru_cache(maxsize=2)
def load(models_root: str) -> SigLIP:
    d = models.require(Path(models_root), "siglip-base-multilingual")
    return SigLIP(d)


_text_cache: dict[str, np.ndarray] = {}


def text_vector(models_root: str, text: str) -> np.ndarray:
    key = models_root + "\x00" + text
    if key not in _text_cache:
        if len(_text_cache) > 4096:
            _text_cache.clear()
        _text_cache[key] = load(models_root).encode_texts([text])[0]
    return _text_cache[key]
