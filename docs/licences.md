# Licence audit

Status: 2026-10-04. Re-run before every release (commands below). The rule: every dependency and every model weight the
default install uses must allow commercial use with no company-size, revenue, user-count or registration limits, and must be
compatible with Metachlorian's own licence.

## Metachlorian

**Apache-2.0** (see [LICENSE](../LICENSE) and [decision 015](decisions/015-licence.md)). The explicit patent grant suits a
project that ships ML pipelines; Apache-2.0 is compatible with Cutawan's MIT licence in both directions of reuse
(MIT code can be included here; our code can be used by MIT projects that keep the notice).

## Model weights used by the default install

| Model | Purpose | Licence | Commercial | Obligations |
|---|---|---|---|---|
| SigLIP base patch16-256 multilingual (Google), our ONNX export | Image/text embeddings, zero-shot labels | Apache-2.0 | Yes | Keep NOTICE; we state that the export is modified (ONNX conversion, embedding table int8) |
| NVIDIA Parakeet TDT 0.6B v3 (sherpa-onnx int8 export) | Speech recognition | CC-BY-4.0 | Yes | **Attribution required**: credited in NOTICE, About → Model credits, and this file |
| OpenAI Whisper base (sherpa-onnx export) | Spoken language identification | MIT | Yes | Keep copyright notice |
| Silero VAD | Voice activity detection | MIT | Yes | Keep notice |
| pyannote segmentation 3.0 (ONNX, ungated copy) | Speaker segmentation | MIT | Yes | Keep notice |
| NVIDIA TitaNet small (sherpa-onnx) | Speaker embeddings | CC-BY-4.0 | Yes | **Attribution required** (as above) |
| CED-mini (weights) | Audio event tagging | Apache-2.0 | Yes | The CED *training code* is GPL-3.0; we do not use or ship it |
| MediaPipe EfficientDet-Lite2 (COCO) | Object and person detection | Apache-2.0 | Yes | Keep notice |
| OpenCV Zoo YuNet 2023mar | Face detection (no identity) | MIT | Yes | Keep notice |
| PP-OCR models bundled in `rapidocr-onnxruntime` | OCR | Apache-2.0 | Yes | Keep notice |
| Qwen3.5 (2B/4B/9B GGUF) — **optional**, not downloaded by default | Captions, fusion | Apache-2.0 | Yes | Keep notice; user installs via llama.cpp/Ollama |

Rejected on licence grounds (details in [research/model-licences.md](research/model-licences.md)): MiniCPM-V (usage
caps/registration), Gemma 1–3 (Gemma terms), Qwen2.5-VL-3B (research licence), LFM2-VL (revenue cap), Moondream 3 (BSL),
Llama vision (community licence), Ultralytics YOLO (AGPL), YOLO-World/YOLOv7/v9 (GPL), InsightFace/SCRFD (non-commercial),
RF-DETR XL/2XL (PML), DEIMv2 (non-commercial since 2026), MobileCLIP (research), jina-clip-v2 / jina rerankers (CC BY-NC),
pyiqa (PolyForm-NC), CoTracker (non-commercial), Reverb diarisation (non-commercial).

## Python dependencies (core)

All permissive (MIT, BSD, Apache-2.0, PSF, ISC, Zlib, CC0) except two MPL-2.0 packages (`certifi`, `tqdm` partially).
MPL-2.0 is file-level copyleft: using unmodified MPL files inside an Apache-2.0 application is allowed; modifications to
those files would have to be published. We do not modify them. Full generated table: [licences-python.md](licences-python.md).

Key packages: FastAPI (MIT), Starlette (BSD-3), Pydantic (MIT), uvicorn (BSD-3), NumPy (BSD-3), OpenCV (Apache-2.0),
ONNX Runtime (MIT), usearch (Apache-2.0), sherpa-onnx (Apache-2.0), RapidOCR (Apache-2.0), PySceneDetect (BSD-3, used only as a
benchmark baseline), LiteRT / ai-edge-litert (Apache-2.0), OpenTimelineIO (Apache-2.0), MCP Python SDK (MIT),
argon2-cffi (MIT), sentencepiece (Apache-2.0), jsonschema (MIT), httpx (BSD-3), watchfiles (MIT), boto3 (Apache-2.0, optional).

## JavaScript dependencies (app)

React (MIT), Vite (MIT), TanStack Query/Router/Virtual (MIT), React Aria Components (Apache-2.0), Zustand (MIT),
Lucide (ISC), Lightning CSS (MPL-2.0, build-time only, not shipped), Electron (MIT), Playwright (Apache-2.0, dev only).
Fonts: Instrument Sans and JetBrains Mono (SIL OFL 1.1; bundled via Fontsource, OFL permits bundling with software).
Generated table: run `npx license-checker --summary` in `app/` (see [licences-js.md](licences-js.md) once generated).

## System tools invoked as separate processes

| Tool | Licence | How we use it | Obligation |
|---|---|---|---|
| FFmpeg | LGPL-2.1+, or GPL when built with libx264 (we use libx264 for proxies) | Executed as a separate program; never linked | Server installs use the system FFmpeg. Desktop installers that bundle an FFmpeg binary must ship its licence and offer its source (as Cutawan already does with `ffmpeg-static`). See OPEN_QUESTIONS Q9 |
| ExifTool (optional) | Artistic/GPL | Executed if present | None for us (not bundled) |
| llama.cpp server / Ollama (optional) | MIT | Separate process, OpenAI-compatible API | None |

## Evaluation footage

Not distributed with the software. Sources and licences per file are in `eval/media/SOURCES.md`; clips with unclear
licences are marked LOCAL-ONLY and are never committed (OPEN_QUESTIONS Q5).

## How to re-run this audit

```bash
cd core && .venv/bin/pip install pip-licenses && .venv/bin/pip-licenses --format=markdown > ../docs/licences-python.md
cd app && npx license-checker --production --summary
python -c "from metachlorian import models; [print(m['name'], m['licence']) for m in models.status('.')]"
```
