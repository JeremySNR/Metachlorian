# 007. OCR, object detection, faces/people and logos

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
Per shot we want:
- **on-screen text**: lower thirds, signs, slates and burnt-in subtitles, with boxes and times;
- **objects**, as counted, boxed classes for filters such as "contains a car" or "≥3 people";
- **faces and people**: count, size and position. These feed the shot-size and role heuristics.
  Recognising *who* someone is is out of scope for v1;
- **logos/brands**, for clearance and sponsorship search.

Everything must run on CPU at reduced frame rate (1-2 fps sampling), and every weight must allow
commercial use with no AGPL/GPL obligations on the product. Detector licences are a minefield:
several "open" detectors are AGPL, GPL, non-commercial or proprietary.

**Build environment constraints.** No GPU, 4 shared CPUs (load average 18-27 during testing), 15 GB
RAM. Hugging Face and download.pytorch.org are blocked, and so is ModelScope (RapidOCR's model host).
Reachable: PyPI, GitHub release downloads, media.githubusercontent.com (Git LFS objects, e.g.
opencv_zoo), storage.googleapis.com (MediaPipe, RF-DETR, OWL-ViT weights), Docker Hub and ghcr.io.
The `mediapipe` 1.0.1 wheel fails to import here: it needs `libEGL.so.1` (apt `libegl1`), which the
sandbox does not have.

## Options considered
### OCR
| Option | Quality | Licence | Hardware / speed | Maturity / community |
|---|---|---|---|---|
| **RapidOCR 3.9.2** (PP-OCR models on ONNX Runtime) | PP-OCRv6 det/rec "small" are **bundled in the wheel**. Strong on scene and overlay text; multilingual rec models available | Apache-2.0 (code; PaddleOCR models Apache-2.0) | CPU, roughly 100-300 ms per frame idle | Very active (release 2026-07-21). Large CN/EN community |
| docTR 1.1 (`python-doctr`) | Strong on documents; good detection + recognition zoo | Apache-2.0 | PyTorch (OnnxTR for ONNX) | Active (Mindee) |
| EasyOCR 1.7.2 | OK for scene text, 80+ languages | Apache-2.0 | PyTorch. Slower | Stale (last release 2024-09) |
| Tesseract 5 | Good on clean documents, poor on video overlays and scene text | Apache-2.0 | CPU, fast | Very mature |
| VLM OCR (GLM-OCR, Granite-Docling, Qwen3.5) | Best at reading layout and context | MIT / Apache-2.0 | GPU preferred | Use for documents and slates, not every frame |

### Closed-set object detection (COCO-80)
| Option | COCO AP50:95 | Licence | Weights reachable here | Notes |
|---|---|---|---|---|
| MediaPipe EfficientDet-Lite0 / Lite2 | 25.7 / 34.0 | Apache-2.0 | GCS (yes) | Tiny and fast. Needs `mediapipe` (libEGL) or a raw TFLite runtime |
| **YOLOX-S** (opencv_zoo ONNX) | 40.5 | Apache-2.0 | media.githubusercontent.com (yes; 36 MB fp32, 9 MB int8) | Plain ONNX, runs in onnxruntime/OpenCV. Dated (2021) but permissive |
| RT-DETR / RT-DETRv2 (r18-r101) | 46.5-54.3 | Apache-2.0 | GitHub releases `lyuwenyu/storage` (yes) | No NMS. PyTorch → ONNX export |
| D-FINE N/S/M/L/X | 42.8-55.8 (more with O365 pre-training) | Apache-2.0 | GitHub releases `Peterande/storage` (yes) | Strong accuracy/latency. ONNX export scripts |
| DEIM (v1, D-FINE based) | +0.2-0.7 over D-FINE | Apache-2.0 | GitHub/Google Drive | Fine |
| **DEIMv2** (2025-26, DINOv3) | 43-57.8 | **"DEIMv2 License": non-commercial only (2026)**. DINOv3 backbone under the custom DINOv3 licence. **Excluded** | n/a | Licence trap |
| **RF-DETR N/S/M/L** (Roboflow) | 48.4 / 53.0 / 54.7 / 56.5. Best fine-tuning transfer (RF100-VL) | Apache-2.0 for N-L. **XL/2XL are PML 1.0 (excluded)** | storage.googleapis.com/rfdetr (yes, ~370-400 MB checkpoints incl. optimiser state) | `rfdetr` 1.11.1 (2026-09-30), very active. ONNX export built in. DINOv2 backbone (Apache-2.0) |
| Ultralytics YOLOv5/8/11/26, YOLOE | 37-57 | **AGPL-3.0** (or paid enterprise licence). **Excluded** | n/a | Licence trap |
| YOLOv7/v9, YOLO-World | n/a | **GPL-3.0**. Excluded | n/a | n/a |
| YOLO-NAS | n/a | **Deci proprietary weights licence**. Excluded | n/a | n/a |

### Open-vocabulary detection / grounding
| Option | Licence | Notes |
|---|---|---|
| OWLv2 (Google, scenic) | Apache-2.0 | Text- **and image-conditioned** (query by example) detection. Checkpoints on GCS `scenic-bucket` (reachable). Heavy (B/16 at 960 px), GPU recommended |
| Grounding DINO (Swin-T) | Apache-2.0 | 694 MB checkpoint on GitHub releases (reachable). Slow on CPU. Grounding DINO 1.5/1.6 are API-only |
| Florence-2 | MIT | One small model for OD, grounding, caption and OCR. HF only |
| VLM grounding (Qwen3-VL/Qwen3.5 boxes, Molmo2 points) | Apache-2.0 | Already loaded for captioning (ADR 004). Good for "is there an X" checks, coarse boxes |
| SAM 3 (Meta, 2025) | Custom "SAM License". Review needed | Concept-prompted segmentation. GPU |

### Faces / people
| Option | Quality | Licence | Notes |
|---|---|---|---|
| **YuNet** (OpenCV `FaceDetectorYN`) | WIDER Face AP 0.834 / 0.824 / 0.708 (easy/med/hard) | MIT | 230 KB ONNX (int8 100 KB) via media.githubusercontent.com. Built into OpenCV. **Tested here: 1 face found on the test image in 26 ms** |
| MediaPipe BlazeFace short- / full-range | Good near-frontal. Full-range handles small faces | Apache-2.0 | `.tflite` on GCS (reachable). Needs the mediapipe runtime |
| SCRFD / RetinaFace / ArcFace (InsightFace) | State of the art | Code MIT, but **models non-commercial research only**. Excluded | Licence trap |
| Person boxes from the COCO detector | n/a | As detector | "person" class gives people count and size |
| Face recognition (SFace, ArcFace) | n/a | n/a | **Out of scope for v1.** Biometric processing (GDPR Art. 9, BIPA, EU AI Act) would need an opt-in design review |

### Logos
There is no permissively licensed, general-purpose logo detector of good quality. The datasets
(LogoDet-3K, OpenLogo, FlickrLogos) are research-only. Practical options:
- OCR for wordmarks;
- VLM "visible brands" tags;
- **OWLv2 image-conditioned detection** against user-supplied logo exemplars;
- CLIP/SigLIP crop similarity against a user's logo library.

## Evidence
- RapidOCR wheel inspected: `rapidocr-3.9.2-py3-none-any.whl` (27 MB) contains
  `models/PP-OCRv6_det_small.onnx`, `PP-OCRv6_rec_small.onnx` and `ch_ppocr_mobile_v2.0_cls_mobile.onnx`.
  Its other models resolve to modelscope.cn (blocked). **Smoke test:** it read the overlay text
  "BREAKING NEWS: Metachlorian 2..." (conf 0.99) plus "unicef" and "WEEKmedia" from the test frame
  offline.
- EfficientDet-Lite COCO mAP (25.69 / 30.55 / 33.97 / 37.70 / 41.96 for Lite0-4) comes from the
  TFLite Model Maker docs
  (https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/g3doc/models/modify/model_maker/object_detection.ipynb).
  MediaPipe model URLs returned 200.
- RF-DETR README benchmark table, which also lists YOLO11/YOLO26 (AGPL), LW-DETR and D-FINE AP and
  licences: `rfdetr` 1.11.1 wheel METADATA, https://github.com/roboflow/rf-detr. The weight URLs in
  `rfdetr/assets/model_weights.py` were checked at 200.
- DEIMv2 licence text: https://github.com/Intellindust-AI-Lab/DEIMv2/blob/main/LICENSE.md
  ("No rights are granted for Commercial Use"). DEIM v1 LICENSE says Apache:
  https://github.com/ShihuaHuang95/DEIM. D-FINE, RT-DETR, Grounding DINO, YOLOX, docTR, EasyOCR and
  scenic LICENSE files read via raw.githubusercontent.com (all Apache-2.0).
- InsightFace README: "models ... available for non-commercial research purposes only"
  (https://github.com/deepinsight/insightface).
- YuNet: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet (MIT; a
  `2026may` dynamic-shape export exists for OpenCV 5's ORT engine).
- Ultralytics licence: PyPI `ultralytics` 8.4.172, `AGPL-3.0`. YOLO-NAS:
  https://github.com/Deci-AI/super-gradients/blob/master/LICENSE.YOLONAS.md.
- OWL-ViT/OWLv2 checkpoints:
  https://github.com/google-research/scenic/tree/main/scenic/projects/owl_vit (GCS links).
- YOLOX-S ran in onnxruntime in the sandbox at about 1.4 s per 640² frame. The CPUs were heavily
  oversubscribed, so this is not a representative benchmark. Re-measure in `eval/` on an idle
  machine.

## Decision
- **OCR: RapidOCR 3.9.x with its bundled PP-OCRv6 small models** (Apache-2.0), run at 1 fps on
  keyframes, plus extra frames when the text-region detector fires.
  - Merge identical strings across consecutive frames into timed text tracks
    (`text`, `bbox`, `t_start`, `t_end`, `conf`), and classify them by zone (lower third, top
    ticker, subtitles, scene).
  - Tesseract is not used by default.
  - Document-like slates can optionally go to the VLM (ADR 004).
- **Objects: RF-DETR-N/S (Apache-2.0) exported to ONNX** as the default COCO detector. It is the best
  permissive accuracy per FLOP, very active, and easy to fine-tune for custom classes.
  - **YOLOX-S (Apache-2.0, opencv_zoo ONNX) is the zero-conversion fallback** used in CI and on
    machines without the exported RF-DETR file.
  - D-FINE-S is the documented alternative if RF-DETR's DINOv2 backbone is too slow on a given CPU.
  - All AGPL/GPL YOLO variants, YOLO-NAS, DEIMv2 and RF-DETR XL/2XL are banned. The model registry
    must refuse them.
- **Open vocabulary: no dedicated detector in the default CPU path.** VLM tags and SigLIP 2 search
  (ADR 005) cover open-vocabulary recall. OWLv2 is the GPU plug-in for boxes and for
  logo-by-example.
- **Faces/people: YuNet (MIT) via OpenCV** for face boxes and landmarks; the person class from the
  object detector for people count. The face-area-to-frame ratio feeds shot-size classification
  (ECU/CU/MCU/MS/WS). No identity embeddings in v1.
- **MediaPipe** (EfficientDet-Lite, BlazeFace, YAMNet) is *not* the default. Its wheel adds GL/EGL
  system dependencies and lower-accuracy models. It stays an optional backend for very low-power
  devices.
- **Logos:** OCR wordmarks + VLM brand tags in v1. Exemplar-based OWLv2 search is a later opt-in.

## Consequences
- The default stack is onnxruntime + OpenCV only, all Apache/MIT, with no system GL libraries.
- Exporting RF-DETR to ONNX needs PyTorch once (from PyPI) at build time, not at runtime. We host
  the resulting ONNX as a release asset (the upstream `.pth` files are about 370-400 MB because they
  include training state, while the exported N/S models are about 100-130 MB fp32).
- COCO-80 classes are coarse (no "drone", "microphone", "slate"). VLM tags fill those gaps. Custom
  classes need fine-tuning, which RF-DETR makes easy.
- The licence gate must be enforced in code (an allow-list of model IDs + SPDX), not by convention.

## Revisit when
- A permissive open-vocabulary detector becomes CPU-viable (an OWLv2 distillation, or Apache-licensed
  YOLO-World-class models).
- RF-DETR changes the licence of the N-L weights, or Roboflow moves them off GCS.
- Users ask for person identity search. That needs a privacy design review first.
- RapidOCR's bundled models change (e.g. PP-OCRv7), or ModelScope-only hosting breaks offline
  installs.

## Recommendation for the builder
- `pip install rapidocr==3.9.2 onnxruntime opencv-python-headless`. The bundled models work offline
  (verified). Do not install `mediapipe` in the default image.
- YuNet: `https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx`
  (the raw.githubusercontent URL serves only the LFS pointer). For OpenCV 5's ORT engine, use the
  `face_detection_yunet_2026may.onnx` dynamic-shape file from the same folder.
- YOLOX-S fallback: `https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx`
  (int8: `..._2022nov_int8.onnx`).
- RF-DETR:
  1. `pip install rfdetr==1.11.1` plus CPU `torch` from PyPI.
  2. Weights: `https://storage.googleapis.com/rfdetr/nano_coco/checkpoint_best_regular.pth`,
     `.../small_coco/checkpoint_best_regular.pth`.
  3. Export to ONNX (`model.export()`), verify AP on COCO val2017 subset, then publish as a
     Metachlorian release asset.
- D-FINE alternative: `https://github.com/Peterande/storage/releases/download/dfinev1.0/dfine_n_coco.pth`.
- MediaPipe models, if ever needed: `https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite`,
  `https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite`.

## Outcome (as built, 2026-10-04)

- **OCR**: RapidOCR (onnxruntime package 1.4.x, bundled PP-OCR models, Apache-2.0) on up to 3 keyframes per shot (first,
  middle, last), angle classifier off for speed; strings de-duplicated per shot, classified as title / lower third /
  burned-in captions by position and change across frames. Upgrade path: rapidocr 3.9 with PP-OCRv6 (same API family).
- **Faces**: YuNet 2023mar (MIT) via `cv2.FaceDetectorYN`, as recommended. On the classroom sample it found 4 of 5 small faces
  where MediaPipe BlazeFace short-range found none.
- **Objects / people count**: MediaPipe EfficientDet-Lite2 (Apache-2.0) run on **LiteRT** (`ai-edge-litert`), not the MediaPipe
  wheel, so there is no EGL/GL dependency (the MediaPipe 1.0 wheel failed on this headless machine with a missing
  `libEGL.so.1`, confirming the research). Anchor decoding implemented in `media/detect.py` and verified visually. This is a
  deliberate v1 shortcut: RF-DETR-N/S (better accuracy) needs a PyTorch→ONNX export step; it is the next detector upgrade
  and drops in as a `people` analyser version bump.
- No identity: faces are counted, sized and positioned only (OPEN_QUESTIONS Q7).
