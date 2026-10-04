# 004. Vision-language model (captions/labels), serving runtime, and fusion LLM

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
For each shot, a local VLM looks at 1-4 keyframes (optionally a short frame strip) and produces:
- a caption,
- shot size and angle,
- subject/role hints ("interviewee", "b-roll", "establishing"),
- free-form tags,
- aerial/indoor/time-of-day guesses.

A second step, **fusion**, turns all analyser outputs into one validated JSON shot record. The
analyser outputs are cuts (003), VLM output, ASR (006), OCR/objects/faces (007) and motion/quality
(008). Fusion must never invent facts that the deterministic analysers did not measure.

Requirements:
- runs on **one consumer GPU (8-12 GB)**, with a **CPU fallback**;
- exposed through an **OpenAI-compatible API** so users can point Metachlorian at any local server;
- **JSON-schema constrained output**;
- weights that allow commercial use with no company-size or MAU limits.

**Build environment constraints.** No GPU, 4 shared CPUs (load average 12-27 during testing), 15 GB
RAM. Blocked: Hugging Face, ollama.com/registry.ollama.ai, download.pytorch.org. Reachable: GitHub
release downloads (llama.cpp `b11382` CPU build verified), ghcr.io (`ggml-org/llama.cpp:server`
verified), and **Docker Hub's `ai/` namespace**. Its OCI artifacts (GGUF + `mmproj` + licence
layers) download anonymously through `registry-1.docker.io`, which was verified by pulling five VLMs.

## Options considered
### Models (all sizes at Q4 unless noted; "Docker ai/" = verified GGUF + mmproj on Docker Hub)
| Option | Quality | Licence | 8-12 GB GPU / CPU | Docker ai/ | Maturity / community |
|---|---|---|---|---|---|
| **Qwen3.5 0.8B / 2B / 4B / 9B** (Mar 2026) | Natively multimodal (image + video), 262k ctx, 201 languages. 4B MMMU ≈77.6, 9B ≈78.4 (vendor). One model does captioning **and** text fusion | **Apache-2.0** | 4B ≈3.4 GB + 0.67 GB mmproj, so it fits 8 GB. 9B ≈6.6 GB fits 12 GB. 0.8B/2B for CPU | Yes: `ai/qwen3.5` 0.8b-9b, many quants | Latest Qwen gen. Huge ecosystem. llama.cpp support. **Thinks by default** (see Evidence) |
| Qwen3-VL 2B / 4B / 8B (Oct 2025) | Strong grounding/OCR. 4B MMMU 67.4 | Apache-2.0 | 4B / 8B on GPU, 2B on CPU | Yes: `ai/qwen3-vl` 2B/4B/8B | Mature. llama.cpp `qwen3vl` arch |
| Gemma 4 E2B / E4B (Apr 2026) | Strong small multimodal. Image + **audio** on E2B/E4B | **Apache-2.0** (first Gemma under Apache) | E4B ≈5 GB + 1 GB mmproj | Yes: `ai/gemma4` e2b/e4b/12b | Google. Broad runtime support |
| Ministral 3 3B / 8B (Dec 2025) | Good vision for size | Apache-2.0 | 3B ≈2.1 GB + 0.8 GB | Yes: `ai/ministral3` | Mistral |
| SmolVLM / SmolVLM2 (256M-2.2B) | Weak captions, but tiny. SmolVLM2 trained for video | Apache-2.0 | CPU-friendly | `ai/smolvlm` 500M (v1 only) | HF team. Slowing cadence |
| Moondream 2 (1.9B) | Good captions/points for size | Apache-2.0 (**Moondream 3 = BSL-1.1, excluded**) | CPU OK | `ai/moondream2` (F16 only, 3.75 GB) | Small team |
| Florence-2 base/large (0.23/0.77B) | Great dense captions, OD and OCR. No instruction following or JSON | MIT | CPU OK | No (HF ONNX only) | 2024. Stale |
| InternVL3.5 1-8B | Strong benchmarks | Apache-2.0 (weights) / MIT (code) | Fits | No (HF GGUF) | Active |
| Molmo2 4B/8B (Dec 2025) | Video grounding, pointing, tracking | Apache-2.0 (some training data third-party NC; Ai2 note) | 8B Q4 fits 12 GB | No. llama.cpp support not verified | Ai2 |
| LLaVA-OneVision-1.5 4B/8B | Fully open training | Apache-2.0 (per repo; verify) | Fits | No | Academic |
| MiniCPM-V 4.5/4.6 | Strong | **MiniCPM Model Licence: commercial use needs registration; free tier capped at <5,000 devices / <1 M DAU. Excluded** | n/a | n/a | n/a |
| Gemma 3 / Gemma 3n | Good | **Gemma Terms of Use + Prohibited Use Policy (flow-down). Excluded as default** | n/a | `ai/gemma3*` | n/a |
| Qwen2.5-VL-3B | Good | **Qwen Research Licence (non-commercial). Excluded** (7B is Apache-2.0; 72B has the Qwen licence MAU clause) | n/a | n/a | n/a |
| LFM2-VL / LFM2.5-VL (Liquid) | Fast on-device | **LFM Open Licence: commercial use only below US$10 M revenue. Excluded** | n/a | n/a | n/a |
| Llama 3.2 Vision | n/a | **Llama Community Licence (700 M MAU cap, EU multimodal restriction). Excluded** | n/a | n/a | n/a |

### Serving runtimes
| Runtime | OpenAI-compatible | JSON-schema output | Images | Licence | Notes |
|---|---|---|---|---|---|
| **llama.cpp `llama-server`** | `/v1/chat/completions`, `/v1/embeddings` | `response_format: {type: json_schema}` → GBNF grammar (also `json_object`) | `image_url` (base64 or URL) via libmtmd; `--mmproj` | MIT | CPU / CUDA / Vulkan / Metal. Release binaries on GitHub, images on ghcr.io. `chat_template_kwargs` per request |
| Ollama | `/v1` compat + native `/api/chat` | `format: <schema>` natively; `response_format` json_schema on `/v1` (issue #18717: key order not preserved on one path) | Yes (registry vision models) | MIT | Easiest UX, but models come from registry.ollama.ai (blocked here). Importing GGUF+mmproj vision models is limited |
| Docker Model Runner | Yes (llama.cpp backend; vLLM backend on GPU) | Same as llama.cpp | Yes | Apache-2.0 (docker/model-runner) | Pulls `ai/*` directly. Needs Docker Desktop/Engine plugin |
| vLLM | Yes | `response_format` json_schema via xgrammar/guidance (strongest) | Yes | Apache-2.0 | GPU-first, safetensors from HF. Best throughput on 12 GB+ for 2-4B BF16/FP8. Its CPU backend is not practical here |
| LM Studio | Yes | `response_format` json_schema | Yes | **Proprietary app** (free to use) | Supported as a "bring your own server", never bundled |

### Fusion LLM
Fusion options:
- **the same VLM in text mode** (Qwen3.5-4B/2B), so no second model is resident;
- Qwen3-4B-Instruct-2507 (Apache-2.0, `ai/qwen3:4b-instruct-2507`);
- Granite 4.1/4.2 3B (Apache-2.0, `ai/granite4.2:3b`);
- SmolLM3-3B (Apache-2.0).

All are served with the same JSON-schema mechanism.

## Evidence
- Docker Hub `ai/` listing (`hub.docker.com/v2/namespaces/ai/repositories`) and manifests/config
  blobs from `registry-1.docker.io` (anonymous token):
  - `ai/qwen3.5:{0.8b-q4_K_XL, 2b-q4_K_XL, 4b-q4_K_M}`: source `unsloth/Qwen3.5-*-GGUF`, layers
    `Qwen3.5-*.gguf` + `mmproj-F16.gguf`, licence `Apache-2.0`, inputTypes text+image.
  - `ai/qwen3-vl:{2B,4B,8B}-UD-Q4_K_XL`: arch `qwen3vl`, licence apache-2.0, mmproj layer.
  - `ai/gemma4:{e2b-q4_K_M,e4b}`: Apache-2.0, mmproj.
  - `ai/ministral3:3B-Q4_K_M`: apache-2.0, mmproj.
  - `ai/smolvlm:500M-Q8_0` (base SmolLM2-360M, apache-2.0).
  - `ai/moondream2:1.5B` (phi2 arch, F16).
  - `ai/gemma3n`: licence `gemma`.
- Five VLMs (0.5-4 GB each) were downloaded from Docker Hub in the sandbox, in under 2 minutes in
  total: qwen3.5 0.8b/2b, qwen3-vl 2B, gemma4 e2b, smolvlm 500M. Only Qwen3.5-2B was kept, at
  `/home/user/models/llm/qwen3.5-2b/`, together with the llama.cpp binary at
  `/home/user/models/llm/llama-b11382/`.
- **llama-server b11382 smoke test (CPU, 4 threads, heavily contended host)** used a 448x300 frame
  with `response_format: json_schema` (caption, enum shot_size, objects[], people_count, indoor):
  - Qwen3.5-0.8B with default settings spent all 300 tokens in `reasoning_content` and returned
    empty `content`. **Qwen3.5 thinks by default.** Send
    `"chat_template_kwargs": {"enable_thinking": false}` (or start the server with reasoning
    disabled) for extraction work.
  - Speeds under that contention: prompt 4.2 tok/s (150 tokens incl. image), decode 16.6 tok/s.
  - **Qwen3.5-2B UD-Q4_K_XL + mmproj-F16, with thinking disabled**, returned schema-valid JSON
    (`finish_reason: stop`, 127 tokens). The output was accurate: "A soccer player in a red and
    blue striped FC Barcelona jersey, mid-action, kicking a yellow soccer ball on a green pitch
    during a match", shot_size `medium`, objects [soccer player, soccer ball, stadium, crowd, …,
    Nike swoosh], people_count 1, indoor false.
  - Timing for that run is not meaningful. The host had a load average of about 16 on 4 vCPUs,
    plus a stray second llama-server, giving 2.6 tok/s prompt and 0.2 tok/s decode. A re-run with
    `-t 3` and no stray server (load still ≈17) gave 5.5 tok/s prompt and 1.1 tok/s decode: 142 s
    wall for one frame, with valid JSON again. On an idle
    4-core x86 the expected order of magnitude is 20-60 tok/s prompt and 10-20 tok/s decode for a
    2B Q4 model. **Re-benchmark in `eval/` on an idle machine.** Note also that JSON-schema grammar
    sampling over Qwen's ~250k vocabulary adds per-token cost on CPU.
- Licences:
  - Qwen3.5 small models Apache-2.0: https://www.therundown.ai/tools/qwen3-5-small,
    https://insiderllm.com/guides/qwen-3-5-small-models-9b-beats-30b/
  - Gemma 4 Apache-2.0: https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/,
    https://venturebeat.com/technology/google-releases-gemma-4-under-apache-2-0-and-that-license-change-may-matter
  - Moondream 3 BSL: https://huggingface.co/moondream/moondream3-preview/blob/main/LICENSE.md
  - MiniCPM-V licence: https://github.com/OpenBMB/MiniCPM-V
  - Molmo2 Apache-2.0: https://allenai.org/blog/molmo2
  - LFM licence: https://www.liquid.ai/lfm-license
  - InternVL3.5: https://huggingface.co/OpenGVLab/InternVL3_5-4B
  - SmolVLM2: https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct
- Runtimes:
  - llama.cpp server README and multimodal doc:
    https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md,
    https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md
  - Ollama structured outputs: https://docs.ollama.com/capabilities/structured-outputs; key-order
    issue: https://github.com/ollama/ollama/issues/18717

## Decision
1. **Protocol, not product.** Metachlorian talks to *any* OpenAI-compatible endpoint. It sends
   `image_url` base64 frames and `response_format: {type: "json_schema", strict: true}`, and
   validates every reply with the same JSON Schema (pydantic) plus one repair retry. Capability
   probing at start-up checks vision, json_schema support and context size.
2. **Bundled/default runtime: llama.cpp `llama-server`** (MIT), from the GitHub release binary or
   `ghcr.io/ggml-org/llama.cpp:server`. Ollama, Docker Model Runner, vLLM and LM Studio are
   documented as alternatives. vLLM is recommended for multi-GPU or batch users.
3. **Default model family: Qwen3.5 (Apache-2.0)**, one model for both captioning and fusion.
   | Machine | Model |
   |---|---|
   | 12 GB GPU | `qwen3.5:9b-q4_K_M` |
   | 8 GB GPU | `qwen3.5:4b-q4_K_M` |
   | CPU | `qwen3.5:2b` (or 0.8b on weak machines), with fewer frames and `--image-max-tokens 256` |

   Always disable thinking for extraction. **Alternatives kept tested:** Qwen3-VL-4B/8B (better
   grounding boxes) and Gemma 4 E4B (Apache-2.0, adds audio understanding).
4. **Fusion = deterministic merge first, LLM second.** Code computes every measured field: times,
   motion labels, counts, loudness, OCR text. The LLM only writes the *derived* fields: summary,
   role, tags, and search keywords. It gets a compact evidence pack and a schema with enums, and
   must cite evidence keys. Outputs failing the schema, or contradicting measured fields, are
   rejected and retried once; if the retry fails, the record keeps the deterministic fields only.
5. The model registry stores the SPDX licence per model, and refuses the excluded families above.

## Consequences
- Users can bring any server and model, while the default stays Apache/MIT end to end.
- Constrained decoding guarantees parseable JSON but not truthful JSON. Validation and evidence
  checks remain necessary.
- Qwen3.5's reasoning default and its hybrid (Gated-DeltaNet) architecture need a recent llama.cpp.
  Pin a minimum build (≥ b11382 tested here) and check `chat_template_kwargs` support.
- CPU-only captioning is slow (seconds to tens of seconds per shot). The CPU profile must caption
  only keyframes, batch overnight, and allow captioning to be disabled.

## Revisit when
- A new Apache/MIT VLM beats Qwen3.5-4B on our caption/tag eval at the same VRAM.
- Ollama's registry becomes reachable in CI, or Ollama adds simple GGUF+mmproj import (making it a
  viable default for non-technical users).
- vLLM gains a practical CPU path, or llama.cpp gains video input for Qwen3.5 (temporal reasoning
  per shot instead of keyframes).
- Any default model changes its licence terms.

## Recommendation for the builder
- llama.cpp: `https://github.com/ggml-org/llama.cpp/releases/download/b11382/llama-b11382-bin-ubuntu-x64.tar.gz`
  (17.7 MB, verified), or `ghcr.io/ggml-org/llama.cpp:server` (manifest verified).
- Models from Docker Hub (OCI artifact, no Docker daemon needed):
  1. `GET https://auth.docker.io/token?service=registry.docker.io&scope=repository:ai/qwen3.5:pull`
  2. `GET https://registry-1.docker.io/v2/ai/qwen3.5/manifests/2b-q4_K_XL` (Accept
     `application/vnd.oci.image.manifest.v1+json`)
  3. `GET /v2/ai/qwen3.5/blobs/<digest>` for `Qwen3.5-2B-UD-Q4_K_XL.gguf` and `mmproj-F16.gguf`.

  Verified tags: `ai/qwen3.5:0.8b-q4_K_XL` (CI), `2b-q4_K_XL`, `4b-q4_K_M`, `9b-q4_K_M`;
  `ai/qwen3-vl:2B-UD-Q4_K_XL`; `ai/gemma4:e2b-q4_K_M`; `ai/smolvlm:500M-Q8_0`.
- Run: `llama-server -m model.gguf --mmproj mmproj.gguf -c 8192 -np 1 --image-max-tokens 256 --port 8080`.
  In each request send `"chat_template_kwargs":{"enable_thinking":false}`, `temperature 0`, and the
  JSON schema.
- On user machines the same models are available as `ollama pull qwen3.5:4b` or from HF
  (`unsloth/Qwen3.5-4B-GGUF`).
