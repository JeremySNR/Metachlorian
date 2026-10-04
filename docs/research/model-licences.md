# Model weight licences (recommended and evaluated)

Status: research note, 2026-10-04. Covers the weights recommended in ADRs 003-008, and the
candidates we rejected on licence grounds. "Commercial OK" means the weights may be used in a
commercial product or service with **no** company-size, revenue, MAU or registration limits.

**Verify before release.** Re-read each upstream licence file when pinning a version: licences have
changed in 2025-26, e.g. DEIMv2 → non-commercial, pyiqa → PolyForm-NC, Gemma 4 → Apache-2.0.
Attribution licences (CC-BY-4.0) require a credit in `NOTICE` and in the app's "Model credits"
screen.

## Recommended (default or fallback)
| Model (weights) | Used for (ADR) | Licence | Source URL (verified reachable from build sandbox unless noted) | Commercial OK | Notes |
|---|---|---|---|---|---|
| PySceneDetect detectors (no weights) | Cuts (003) | BSD-3-Clause | https://pypi.org/project/scenedetect/ | Yes | Algorithmic |
| TransNetV2 | Cuts, optional tier (003) | MIT | PyPI wheel `transnetv2-pytorch==1.0.5` (bundles `transnetv2-pytorch-weights.pth`); upstream https://github.com/soCzech/TransNetV2 | Yes | Export to ONNX once |
| Qwen3.5 0.8B/2B/4B/9B (GGUF + mmproj) | VLM + fusion (004) | Apache-2.0 | Docker Hub `ai/qwen3.5` (e.g. `registry-1.docker.io/v2/ai/qwen3.5/manifests/4b-q4_K_M`); HF `Qwen/Qwen3.5-*` | Yes | Disable thinking for extraction |
| Qwen3-VL 2B/4B/8B Instruct | VLM alternative (004) | Apache-2.0 | Docker Hub `ai/qwen3-vl` | Yes | Better grounding boxes |
| Gemma 4 E2B/E4B | VLM alternative (004) | Apache-2.0 | Docker Hub `ai/gemma4` | Yes | Unlike Gemma 1-3, Gemma 4 is Apache-2.0 |
| Ministral 3 3B/8B | VLM alternative (004) | Apache-2.0 | Docker Hub `ai/ministral3` | Yes | n/a |
| SmolVLM-500M-Instruct | CI smoke test (004) | Apache-2.0 | Docker Hub `ai/smolvlm:500M-Q8_0` | Yes | Low quality |
| Qwen3-4B-Instruct-2507 / Granite 4.2 3B | Text-only fusion alternative (004) | Apache-2.0 | Docker Hub `ai/qwen3:4b-instruct-2507`, `ai/granite4.2:3b` | Yes | n/a |
| SigLIP 2 (B/16-256, So400m) | Image-text embeddings (005) | Apache-2.0 | https://storage.googleapis.com/big_vision/siglip2/siglip2_b16_256.npz + https://storage.googleapis.com/big_vision/gemma_tokenizer.model; HF `google/siglip2-*` | Yes | Convert npz → ONNX |
| OpenCLIP ViT-B-32 `laion2b_s34b_b79k` (ONNX) | Embedding fallback/CI (005) | MIT | https://clip-as-service.s3.us-east-2.amazonaws.com/models-436c69702d61732d53657276696365/onnx/ViT-B-32-laion2b-s34b-b79k/visual.onnx (+ `textual.onnx`) | Yes | LAION-2B training data. Some downstream users do their own data-provenance review |
| OpenAI CLIP ViT-B/32 (ONNX) | Embedding fallback (005) | MIT | `.../onnx/ViT-B-32/visual.onnx`, `textual.onnx` (same bucket) | Yes | n/a |
| Qwen3-Embedding-0.6B (GGUF) | Transcript/caption text (005) | Apache-2.0 | Docker Hub `ai/qwen3-embedding:0.6b-q8_0` | Yes | 1024-d, MRL |
| nomic-embed-text-v1.5 / v2-moe | Text alternative (005) | Apache-2.0 | Docker Hub `ai/nomic-embed-text-v1.5`, `ai/nomic-embed-text-v2-moe` | Yes | n/a |
| Parakeet-TDT-0.6B-v3 (int8 ONNX) | ASR (006) | CC-BY-4.0 | https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2 | Yes (attribution) | 25 EU languages |
| Whisper tiny.en / small / turbo / large-v3 (ONNX) | ASR fallback (006) | MIT | `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-{tiny.en,small,turbo,large-v3}.tar.bz2` | Yes | n/a |
| Distil-Whisper large-v3.5 | ASR (English, CPU) (006) | MIT | `.../asr-models/sherpa-onnx-whisper-distil-large-v3.5.tar.bz2` | Yes | English only |
| Moonshine base (English) | Light English ASR (006) | MIT (English models only) | `.../asr-models/sherpa-onnx-moonshine-base-en-quantized-2026-02-27.tar.bz2` | Yes (English) | Non-English Moonshine = Community Licence (NC) |
| Silero VAD | VAD (006) | MIT | https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx | Yes | n/a |
| pyannote segmentation-3.0 (ONNX) | Diarisation (006) | MIT | https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2 | Yes | Ungated copy. LICENSE file included |
| 3D-Speaker CAM++ (en, VoxCeleb) | Speaker embeddings (006) | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx | Yes | n/a |
| NeMo TitaNet-small | Speaker embeddings, alternative (006) | CC-BY-4.0 | `.../speaker-recongition-models/nemo_en_titanet_small.onnx` | Yes (attribution) | n/a |
| CED-mini / CED-base | Audio tagging (006) | Apache-2.0 (weights, HF `mispeech/ced-*`) | https://github.com/k2-fsa/sherpa-onnx/releases/download/audio-tagging-models/sherpa-onnx-ced-mini-audio-tagging-2024-04-19.tar.bz2 | Yes | The training-code repo is GPL-3.0. We do not use or ship it |
| PP-OCRv6 det/rec small + PP-OCR cls (ONNX) | OCR (007) | Apache-2.0 | Bundled in PyPI `rapidocr==3.9.2` wheel | Yes | Other variants are on modelscope.cn (blocked here) |
| RF-DETR N / S (COCO) | Object detection (007) | Apache-2.0 | https://storage.googleapis.com/rfdetr/nano_coco/checkpoint_best_regular.pth, `.../small_coco/checkpoint_best_regular.pth` | Yes | XL/2XL are PML-1.0 (not OK) |
| YOLOX-S (ONNX, opencv_zoo) | Detection fallback/CI (007) | Apache-2.0 | https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx | Yes | n/a |
| D-FINE N-X (COCO) | Detection alternative (007) | Apache-2.0 | https://github.com/Peterande/storage/releases/download/dfinev1.0/dfine_n_coco.pth | Yes | n/a |
| RT-DETRv2 | Detection alternative (007) | Apache-2.0 | https://github.com/lyuwenyu/storage/releases/download/v0.2/rtdetrv2_r18vd_120e_coco_rerun_48.1.pth | Yes | n/a |
| YuNet face detector | Faces (007) | MIT | https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx | Yes | Use the media.githubusercontent URL; raw.githubusercontent serves only the LFS pointer |
| MediaPipe EfficientDet-Lite0/2, BlazeFace, YAMNet | Optional low-power backend (006/007) | Apache-2.0 | https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite, `.../face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite`, `.../audio_classifier/yamnet/float32/latest/yamnet.tflite` | Yes | `mediapipe` wheel needs `libEGL.so.1` |
| OWLv2 B/16 | Open-vocab / logo-by-example, GPU plug-in (007) | Apache-2.0 | https://storage.googleapis.com/scenic-bucket/owl_vit/checkpoints/owl2-b16-960-st-ngrams_c7e1b9a (listed in scenic README; not fetched) | Yes | n/a |
| Grounding DINO Swin-T | Open-vocab, GPU plug-in (007) | Apache-2.0 | https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth | Yes | n/a |
| BRISQUE model (OpenCV contrib) | Image quality (008) | Apache-2.0 | https://raw.githubusercontent.com/opencv/opencv_contrib/4.x/modules/quality/samples/brisque_model_live.yml (+ `brisque_range_live.yml`) | Yes | n/a |
| RAFT (opencv_zoo ONNX) | Dense-flow evaluation only (008) | BSD-3-Clause (upstream RAFT) | https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/optical_flow_estimation_raft/optical_flow_estimation_raft_2023aug.onnx | Yes | Not in default path |

## Watch list (permissive, not yet adopted)
| Model | Licence | Why not yet |
|---|---|---|
| OmniShotCut v1.5 | MIT | CUDA/PyTorch, HF-only weights, 5 months old (003) |
| Perception Encoder PE-Core / PE-AV | Apache-2.0 | HF-only. Evaluate vs SigLIP 2 (005) |
| Qwen3-VL-Embedding-2B | Apache-2.0 | GPU-oriented video embeddings (005) |
| VideoPrism-LvT | Apache-2.0 | JAX-only (005) |
| LAION-CLAP / MS-CLAP | Apache-2.0 weights (CC0 repo) / MIT | Text-to-audio search not in v1 (005) |
| Molmo2 4B/8B | Apache-2.0 (some third-party training data NC; read Ai2's note) | No verified GGUF/llama.cpp path (004) |
| InternVL3.5, LLaVA-OneVision-1.5 | Apache-2.0 (verify per checkpoint) | Not on Docker Hub. Similar to Qwen3.5 (004) |
| Florence-2 | MIT | No JSON/instruction following. HF-only ONNX (004/007) |
| Moondream 2 | Apache-2.0 | Weaker than Qwen3.5 at similar size (004) |
| EfficientAT mn10 | MIT | Needs ONNX export. CED is already in sherpa-onnx (006) |
| PANNs, AST, BEATs | MIT / BSD-3 / MIT | Heavier, or the weights host is unreachable here (006) |
| pyannote speaker-diarization-community-1 | CC-BY-4.0, **gated** | Gating breaks unattended download. Opt-in plug-in (006) |
| Canary-180M-flash | CC-BY-4.0 | en/es/de/fr only (006) |
| CameraBench Qwen2.5-VL-7B fine-tune | Base Apache-2.0. Fine-tune/dataset licence **unverified** | GPU-only. Verify licence (008) |

## Rejected on licence (do not ship, do not auto-download)
| Model | Licence | Problem |
|---|---|---|
| Ultralytics YOLOv5/v8/11/26, YOLOE | AGPL-3.0 (or paid enterprise) | Copyleft over network use |
| YOLOv7, YOLOv9, YOLO-World, YOLOv6 | GPL-3.0 | Copyleft |
| YOLO-NAS | Deci proprietary weights licence | Restrictive |
| DEIMv2 | "DEIMv2 License" (2026): non-commercial only; DINOv3 licence for L/X backbones | No commercial use |
| RF-DETR XL / 2XL | PML-1.0 (Roboflow) | Platform licence, not open |
| SCRFD / RetinaFace / ArcFace (InsightFace model zoo) | Non-commercial research only | No commercial use |
| MobileCLIP / MobileCLIP2, Apple DFN CLIP | Apple ML Research Model licence | Research only |
| jina-clip-v2 (and jina-embeddings-v3/v4) | CC-BY-NC-4.0 / Qwen research-based | Non-commercial |
| MetaCLIP / MetaCLIP 2 | CC-BY-NC-4.0 (verify) | Non-commercial |
| Qwen2.5-VL-3B | Qwen Research Licence | Non-commercial |
| Qwen2.5-VL-72B, Qwen 72B-class | Qwen Licence (100 M MAU clause) | Usage cap |
| Gemma 1/2/3, Gemma 3n, EmbeddingGemma, PaliGemma | Gemma Terms of Use + Prohibited Use Policy | Flow-down use restrictions, remote enforcement clause. Not OSI. Avoid as defaults |
| Llama 3.x / Llama 3.2 Vision | Llama Community Licence | 700 M MAU cap, EU multimodal restriction, AUP |
| MiniCPM-V / MiniCPM-o | MiniCPM Model Licence | Commercial use needs registration; free tier only for <5,000 devices / <1 M DAU |
| LFM2-VL / LFM2.5 (Liquid AI) | LFM Open Licence v1.0 | Commercial use only below US$10 M revenue |
| Moondream 3 | BSL-1.1 + additional use grant | Competing-service restriction |
| Reverb diarization / Reverb ASR (Rev) | Rev Model Non-Production Licence | Non-commercial |
| Moonshine non-English models | Moonshine Community Licence | Non-commercial |
| CoTracker / CoTracker3 | CC-BY-NC-4.0 | Non-commercial |
| pyiqa (library) | PolyForm-Noncommercial-1.0.0 (since 2026) | Non-commercial (library licence, affects its bundled metric code) |

## Pending licence review
SenseVoice-Small (FunASR Model Licence v1.1, custom, allows commercial use with attribution), Qwen3-ASR and Cohere Transcribe 03-2026 (as packaged by sherpa-onnx), SAM 3 (SAM Licence), VGGT, MegaSaM, PERSIST code.
