"""Local model registry and download manager.

Every model the default install uses is listed here with its licence and
source. Weights live in ``<models_dir>/<name>/``. ``metachlorian models fetch``
downloads what is missing; nothing is downloaded implicitly during analysis.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHERPA = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
MEDIAPIPE = "https://storage.googleapis.com/mediapipe-models"
# Metachlorian publishes ONNX exports it makes itself (reproducible with
# scripts/export_siglip.py) as release assets.
MC_RELEASE = os.environ.get("METACHLORIAN_MODEL_MIRROR", "https://github.com/JeremySNR/Metachlorian/releases/download/models-v1")


@dataclass
class ModelSpec:
    name: str
    purpose: str
    licence: str
    source: str
    files: list[str]
    urls: list[str] = field(default_factory=list)  # tar.bz2 archives are extracted
    size_mb: float = 0
    default: bool = True
    tier: str = "cpu"  # cpu | gpu

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


SPECS: dict[str, ModelSpec] = {s.name: s for s in [
    ModelSpec("siglip-base-multilingual", "Visual and text embeddings for semantic search and zero-shot tags", "Apache-2.0",
              "google/siglip-base-patch16-256-multilingual (ONNX export)", ["vision.onnx", "text.q.onnx", "spiece.model", "config.json"],
              [f"{MC_RELEASE}/siglip-base-multilingual.tar.bz2"], 910),
    ModelSpec("parakeet-tdt-0.6b-v3", "Speech recognition with word timings, 25 European languages", "CC-BY-4.0",
              "nvidia/parakeet-tdt-0.6b-v3 via sherpa-onnx", ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"],
              [f"{SHERPA}/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2"], 670),
    ModelSpec("whisper-base", "Spoken language identification (and fallback ASR for languages Parakeet lacks)", "MIT",
              "openai/whisper-base via sherpa-onnx", ["base-encoder.int8.onnx", "base-decoder.int8.onnx", "base-tokens.txt"],
              [f"{SHERPA}/asr-models/sherpa-onnx-whisper-base.tar.bz2"], 160),
    ModelSpec("silero-vad", "Voice activity detection", "MIT", "snakers4/silero-vad via sherpa-onnx", ["silero_vad.onnx"],
              [f"{SHERPA}/asr-models/silero_vad.onnx"], 1),
    ModelSpec("pyannote-segmentation-3.0", "Speaker segmentation for diarisation", "MIT", "pyannote/segmentation-3.0 via sherpa-onnx",
              ["model.onnx"], [f"{SHERPA}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"], 6),
    ModelSpec("titanet-small", "Speaker embeddings for diarisation", "CC-BY-4.0", "nvidia/speakerverification_en_titanet_small via sherpa-onnx",
              ["nemo_en_titanet_small.onnx"], [f"{SHERPA}/speaker-recongition-models/nemo_en_titanet_small.onnx"], 40),
    ModelSpec("ced-mini", "Audio event tagging (AudioSet 527 classes)", "Apache-2.0", "mispeech/ced-mini via sherpa-onnx",
              ["model.int8.onnx", "class_labels_indices.csv"],
              [f"{SHERPA}/audio-tagging-models/sherpa-onnx-ced-mini-audio-tagging-2024-04-19.tar.bz2"], 11),
    ModelSpec("efficientdet-lite2", "Object and person detection (COCO 80 classes)", "Apache-2.0", "MediaPipe EfficientDet-Lite2",
              ["efficientdet_lite2.tflite"], [f"{MEDIAPIPE}/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite"], 23),
    ModelSpec("yunet", "Face detection (counts, sizes, positions; no identity)", "MIT", "OpenCV Zoo YuNet 2023mar",
              ["face_detection_yunet_2023mar.onnx"],
              ["https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"], 0.2),
    ModelSpec("sface", "Face recognition embeddings for naming people (local only, opt-in setting)", "Apache-2.0",
              "OpenCV Zoo SFace 2021dec", ["face_recognition_sface_2021dec.onnx"],
              ["https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"], 37),
    ModelSpec("blazeface-short", "Face detection, close range (legacy fallback)", "Apache-2.0", "MediaPipe BlazeFace short range",
              ["blaze_face_short_range.tflite"], [f"{MEDIAPIPE}/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"], 0.2,
              default=False),
]}

_lock = threading.Lock()


def model_dir(models_root: Path, name: str) -> Path:
    return Path(models_root) / name


def status(models_root: Path) -> list[dict[str, Any]]:
    out = []
    for s in SPECS.values():
        d = model_dir(models_root, s.name)
        present = all((d / f).exists() for f in s.files)
        out.append({**s.as_dict(), "installed": present, "path": str(d)})
    return out


def installed(models_root: Path, name: str) -> bool:
    s = SPECS[name]
    d = model_dir(models_root, name)
    return all((d / f).exists() for f in s.files)


def require(models_root: Path, name: str) -> Path:
    from .analysers.base import Unavailable

    if not installed(models_root, name):
        raise Unavailable(f"model '{name}' is not installed. Run: metachlorian models fetch {name}")
    return model_dir(models_root, name)


def fetch(models_root: Path, name: str, progress=print) -> Path:
    spec = SPECS[name]
    d = model_dir(models_root, name)
    if installed(models_root, name):
        return d
    d.mkdir(parents=True, exist_ok=True)
    for url in spec.urls:
        tmp = d / (".download-" + hashlib.sha1(url.encode()).hexdigest()[:8])
        progress(f"downloading {url}")
        with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        if url.endswith((".tar.bz2", ".tar.gz", ".tgz")):
            with tarfile.open(tmp) as tf:
                for m in tf.getmembers():
                    if not m.isfile():
                        continue
                    base = os.path.basename(m.name)
                    if base in spec.files or any(base == os.path.basename(x) for x in spec.files):
                        src = tf.extractfile(m)
                        assert src is not None
                        with open(d / base, "wb") as out:
                            shutil.copyfileobj(src, out)
            tmp.unlink()
        else:
            tmp.replace(d / os.path.basename(url))
    if not installed(models_root, name):
        raise RuntimeError(f"download of {name} finished but files are missing: {spec.files}")
    return d


def install_from(models_root: Path, name: str, src_dir: Path) -> Path:
    """Install from a local directory (offline installs, air-gapped NAS)."""
    spec = SPECS[name]
    d = model_dir(models_root, name)
    d.mkdir(parents=True, exist_ok=True)
    for f in spec.files:
        cand = list(Path(src_dir).rglob(f))
        if not cand:
            raise FileNotFoundError(f"{f} not found under {src_dir}")
        target = d / f
        if not target.exists():
            try:
                os.link(cand[0], target)
            except OSError:
                shutil.copy2(cand[0], target)
    return d


def ort_session(path: Path, threads: int | None = None):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = threads or int(os.environ.get("METACHLORIAN_THREADS", "0") or 0) or max(1, (os.cpu_count() or 2) // 2)
    so.inter_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = [p for p in ("CUDAExecutionProvider", "CoreMLExecutionProvider", "DmlExecutionProvider") if p in ort.get_available_providers()]
    return ort.InferenceSession(str(path), sess_options=so, providers=providers + ["CPUExecutionProvider"])


_cache: dict[tuple[str, str], Any] = {}


def cached(key: tuple[str, str], factory):
    with _lock:
        if key not in _cache:
            _cache[key] = factory()
        return _cache[key]
