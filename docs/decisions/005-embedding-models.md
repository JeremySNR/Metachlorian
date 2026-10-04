# 005. Embedding models (image-text, video, transcript text, audio)

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
Shot search needs vectors in four places:
1. **Image-text joint space.** Embed keyframes, and embed free-text queries like "drone shot over a
   harbour at dusk".
2. **Video-native embedding.** Optional. It captures motion and actions that single keyframes miss.
3. **Text embedding** of transcripts, captions and OCR, for semantic search and RAG by MCP agents.
4. **Audio embedding.** Optional. It supports "find shots that sound like rain" and text-to-audio
   search.

These vectors go into the vector index (sqlite-vec / LanceDB / pgvector class). Dimension, size,
multilingual queries and ONNX/GGUF availability matter as much as benchmark scores. All weights
must allow commercial use with no company-size limits.

**Build environment constraints.** No GPU, 4 shared CPUs, 15 GB RAM. Hugging Face and
download.pytorch.org are blocked. PyPI, GitHub releases, storage.googleapis.com, Docker Hub and
ghcr.io are reachable. Also verified reachable: the `clip-as-service` S3 bucket
(`clip-as-service.s3.us-east-2.amazonaws.com`), which hosts ONNX exports of OpenAI CLIP and OpenCLIP.
Not reachable: openaipublic.azureedge.net (the original OpenAI CLIP `.pt` files), Apple's CDN, and the
qdrant-fastembed GCS bucket (403).

## Options considered
### Image-text
| Option | Quality | Licence | Dim | ONNX / weights source | Speed (CPU) | Maturity / community |
|---|---|---|---|---|---|---|
| OpenAI CLIP ViT-B/32, ViT-L/14 | Baseline: IN-1k zero-shot ~63 % (B/32) and ~75.5 % (L/14). English only | MIT | 512 / 768 | ONNX on clip-as-service S3 (reachable) | B/32 is fast (~4.4 GFLOPs) | Frozen since 2021. Ubiquitous |
| OpenCLIP LAION-2B (ViT-B-32 `laion2b_s34b_b79k`, ViT-L-14, ViT-H-14) | Better than OpenAI CLIP at the same size (B/32 ~66 %, H/14 ~78 %) | MIT (code and weights) | 512 / 768 / 1024 | ONNX for B-32/L-14/H-14 on clip-as-service S3. Native weights on HF | Same as CLIP | `open-clip-torch` 3.3.0 (2026-02). Active |
| **SigLIP 2** (Google, 2025) | Beats SigLIP and other open baselines on zero-shot classification and retrieval at every size. **Multilingual** (Gemma tokenizer). Better localisation and dense features | Apache-2.0 | 768 (B), 1024 (L), 1152 (So400m) | JAX `.npz` + tokenizer on storage.googleapis.com/big_vision (reachable). ONNX exports on HF | B/16 ≈ ViT-B cost | Widely adopted. In transformers, and the vision tower for many VLMs |
| SigLIP (v1) | A bit below SigLIP 2. i18n variant exists | Apache-2.0 | 768-1152 | GCS `.npz` (reachable). HF | Same | Mature |
| Meta Perception Encoder PE-Core (B16/L14/G14) | PE-Core-G beats SigLIP 2 on zero-shot image tasks and InternVideo2 on most zero-shot video tasks | Apache-2.0 (all PE checkpoints) | 1024 (B/L) | HF only. In open_clip/timm | B16-224 is cheap | 2025, NeurIPS paper. Active repo |
| MobileCLIP / MobileCLIP2 (Apple) | Best accuracy per latency on mobile | **Apple ML Research Model licence: research only, no commercial use** | 512-768 | HF / Apple CDN | Very fast | Excluded on licence |
| jina-clip-v2 | Strong multilingual | **CC-BY-NC-4.0**. Excluded (v1 is Apache-2.0 but weaker) | 1024 | HF | Medium | n/a |
| nomic-embed-vision-v1.5 | Aligned with nomic-embed-text-v1.5, so one space for images and text | Apache-2.0 (relicensed from CC-BY-NC) | 768 | HF. The text tower is GGUF on Docker Hub `ai/nomic-embed-text-v1.5` | Medium | Smaller community |
| MetaCLIP / MetaCLIP 2, Apple DFN CLIP | Strong | MetaCLIP weights CC-BY-NC. DFN weights under Apple research terms. **Excluded** (verify before reconsidering) | n/a | n/a | n/a | n/a |

### Video-native (optional tier)
| Option | Notes | Licence |
|---|---|---|
| Qwen3-VL-Embedding-2B (Jan 2026) | Text, image, video and screenshots in one space. 2048-d with MRL (Matryoshka, so it can truncate). MMEB-v2 retrieval avg 73.4 (video 53.6). Needs a GPU in practice | Apache-2.0 |
| VideoPrism-LvT B/L (Google, Jul 2025) | Video-text encoders: 248 M / 580 M parameters. JAX | Apache-2.0 |
| PE-Core video / PE-AV (Meta, Dec 2025) | PE-AV embeds audio, video, audio-video and text in one joint space | Apache-2.0 |
| Mean-pooled SigLIP 2 over 3-5 frames per shot | Cheap baseline. Loses motion, keeps content | Apache-2.0 |

### Transcript / caption text
| Option | MMTEB (multilingual mean) | Licence | Dim | Availability here |
|---|---|---|---|---|
| **Qwen3-Embedding-0.6B** | 64.33 | Apache-2.0 | 1024 (MRL 32-1024), 32k ctx | GGUF on Docker Hub `ai/qwen3-embedding:0.6b` (q8_0, 0.64 GB) |
| multilingual-e5-large-instruct | 63.22 | MIT | 1024 | HF only |
| EmbeddingGemma-300M | 61.15 | **Gemma Terms of Use** (use restrictions flow down). Flagged | 768 (MRL) | Docker `ai/embeddinggemma` |
| BGE-M3 | 59.56 (also gives sparse and ColBERT vectors) | MIT | 1024 | HF only |
| nomic-embed-text-v1.5 / v2-moe | v1.5 English-centric, v2 multilingual | Apache-2.0 | 768 (MRL) | Docker `ai/nomic-embed-text-v1.5`, `ai/nomic-embed-text-v2-moe` |
| granite-embedding-multilingual 278M | Lower than Qwen3 per MB | Apache-2.0 | 768 | Docker `ai/granite-embedding-multilingual` |

### Audio
| Option | Notes | Licence |
|---|---|---|
| LAION-CLAP (HTSAT) | Text-to-audio retrieval. 512-d | Repo CC0-1.0. HF weights Apache-2.0. The training data mixes sources, so check the attribution notes |
| Microsoft CLAP (msclap 2023) | Text-to-audio. 1024-d | MIT |
| CED-mini/base outputs | The 527-d AudioSet probability vector (or the penultimate features, via a custom ONNX export) gives audio-to-audio similarity only, not text-aligned. Comes free with tagging (ADR 006) | Apache-2.0 weights (code repo is GPL-3.0, which we do not use) |
| PE-AV | Joint audio, video and text space. Could replace both CLIP and CLAP on GPU machines | Apache-2.0 |

## Evidence
- SigLIP 2 paper (Apache-2.0 checkpoints): https://arxiv.org/abs/2502.14786. Weights checked
  reachable, e.g.
  `https://storage.googleapis.com/big_vision/siglip2/siglip2_b16_256.npz` (1.50 GB),
  `.../siglip2_so400m14_224.npz` (4.54 GB), tokenizer
  `https://storage.googleapis.com/big_vision/gemma_tokenizer.model` (4.2 MB).
- Perception Encoder: https://github.com/facebookresearch/perception_models (all PE checkpoints
  Apache-2.0). Paper: https://papers.neurips.cc/paper_files/paper/2025/file/57bc0a850255e2041341bf74c7e2b9fa-Paper-Conference.pdf.
- MobileCLIP2 licence (research only): https://huggingface.co/apple/MobileCLIP2-B/blob/main/LICENSE,
  https://github.com/apple/ml-mobileclip/blob/main/LICENSE_MODELS.
- jina-clip-v2 CC-BY-NC: https://jina.ai/models/jina-clip-v2/. Nomic vision relicensed to Apache-2.0:
  https://www.nomic.ai/news/nomic-embed-vision.
- Qwen3-VL-Embedding: https://github.com/QwenLM/Qwen3-VL-Embedding, https://arxiv.org/abs/2601.04720.
- VideoPrism (Apache-2.0, LvT released 2025-07-16): https://github.com/google-deepmind/videoprism.
- PE-AV: https://huggingface.co/facebook/pe-av-large, https://arxiv.org/abs/2512.19687.
- MMTEB numbers: Qwen3-Embedding model card https://huggingface.co/Qwen/Qwen3-Embedding-0.6B and
  EmbeddingGemma paper https://arxiv.org/abs/2509.20354.
- LAION-CLAP: https://github.com/LAION-AI/CLAP (CC0 repo). MS CLAP: https://github.com/microsoft/CLAP
  (MIT). CED: https://github.com/RicherMans/CED (repo LICENSE is GPL-3.0, checked via
  raw.githubusercontent.com; the HF weights `mispeech/ced-*` are Apache-2.0).
- clip-as-service ONNX URLs come from its source
  (https://github.com/jina-ai/clip-as-service/blob/main/server/clip_server/model/clip_onnx.py) and
  were checked with HEAD requests from the sandbox (200).
- Docker Hub `ai/` embedding repos were listed through `hub.docker.com/v2/namespaces/ai/repositories`.
  Their manifests and licence fields were read from `registry-1.docker.io`. `ai/qwen3-embedding`
  declares Apache-2.0. `ai/embeddinggemma` declares `gemma`.

## Decision
- **Image-text default: SigLIP 2 ViT-B/16-256 (Apache-2.0), 768-d, ONNX on ONNX Runtime.** It is
  multilingual, which matters for non-English libraries. It beats CLIP/OpenCLIP at equal cost, and
  is the most-ported encoder. Store L2-normalised fp16 vectors. Offer `so400m14-224` (1152-d) as a
  "quality" preset for GPU users.
  - Embed 1 frame per second inside each shot, plus the keyframe. The shot vector is the mean of
    the frame vectors. Frame vectors are kept for sub-shot splitting (ADR 003) and in-shot moment
    search.
- **Sandbox/CI fallback: OpenCLIP ViT-B-32 `laion2b_s34b_b79k` ONNX (MIT)** from the
  clip-as-service S3 bucket. It is reachable today and needs no conversion. It keeps the pipeline
  testable before SigLIP 2 is converted.
- **Video-native: not in v1.** Shots are short, and averaging frames covers most search needs.
  Re-evaluate Qwen3-VL-Embedding-2B and PE-AV as GPU plug-ins. Both are Apache-2.0.
- **Text: Qwen3-Embedding-0.6B (Apache-2.0)**, truncated via MRL to 512-d (or kept at 1024-d), served
  by the same `llama-server --embeddings` used for the VLM (ADR 004) from the Docker Hub GGUF. An
  ONNX export is the alternative for pure-Python installs. EmbeddingGemma is not the default because
  of the Gemma terms.
- **Audio: no text-to-audio embedding in v1.** Audio search uses CED AudioSet tags plus transcripts
  (ADR 006). Store the CED 527-d probability vector (free with tagging) for "sounds like this" similarity.
  LAION-CLAP is the planned opt-in (Apache-2.0 weights).

## Consequences
- One vision encoder (SigLIP 2) gives text-to-image search, near-duplicate detection and the
  sub-shot drift signal.
- Embedding versions must be tracked per vector (`model_id`, `dim`, `preprocess_hash`), so that
  switching from the OpenCLIP fallback to SigLIP 2 triggers a re-index, never mixed spaces.
- SigLIP 2 needs a one-off conversion (npz → PyTorch → ONNX) and the Gemma SentencePiece tokenizer.
  The tokenizer runs in Python via `sentencepiece` (PyPI), or ONNX Runtime Extensions.
- 768-d fp16 × 1 fps × 1,000 h of footage is about 5.5 GB of vectors, which is fine for a
  disk-backed index. Per-shot means are much smaller.

## Revisit when
- An Apache/MIT encoder beats SigLIP 2-B by more than 3 points on our shot-retrieval eval at similar
  cost (watch PE-Core-B16, and SigLIP successors).
- Qwen3-VL-Embedding or PE-AV ship small CPU-viable ONNX/GGUF builds.
- Users ask for "sounds like" text queries, which would add CLAP.

## Recommendation for the builder
- Fallback, testable now (MIT, OpenCLIP ViT-B-32 LAION-2B, 512-d):
  - `https://clip-as-service.s3.us-east-2.amazonaws.com/models-436c69702d61732d53657276696365/onnx/ViT-B-32-laion2b-s34b-b79k/visual.onnx`
  - `.../ViT-B-32-laion2b-s34b-b79k/textual.onnx`
  - OpenAI ViT-B-32 ONNX is also confirmed reachable: `.../onnx/ViT-B-32/visual.onnx` (351 MB) and
    `textual.onnx` (254 MB).
  - Tokenise with `open_clip`'s BPE vocabulary (`bpe_simple_vocab_16e6.txt.gz`, bundled in the
    `open-clip-torch` PyPI wheel).
- Default (SigLIP 2, Apache-2.0):
  1. Download `https://storage.googleapis.com/big_vision/siglip2/siglip2_b16_256.npz` and
     `https://storage.googleapis.com/big_vision/gemma_tokenizer.model`.
  2. Convert with the `transformers` SigLIP 2 conversion script (PyPI `transformers` + CPU `torch`).
  3. Export the vision and text towers separately to ONNX, check cosine parity against JAX/PyTorch,
     and publish them as Metachlorian GitHub release assets.
  4. On user machines, `onnx-community`/Google HF repos are an equivalent source.
- Text: pull the GGUF from Docker Hub `ai/qwen3-embedding:0.6b-q8_0`. The blob URLs come from
  `https://registry-1.docker.io/v2/ai/qwen3-embedding/manifests/0.6b-q8_0` (anonymous token from
  `auth.docker.io`). Serve it with `llama-server -m Qwen3-Embedding-0.6B-Q8_0.gguf --embeddings --pooling last`.

## Outcome (as built, 2026-10-04)

- **Image-text: SigLIP (v1) base patch16-256 *multilingual*** (Apache-2.0, 768-d), exported to ONNX by
  `scripts/export_siglip.py` (vision fp32; text tower with its 250k-token embedding table quantised to 8 bits, cosine to fp32
  ≥ 0.998 on test prompts; tokenizer re-implemented with sentencepiece and checked token-for-token against Hugging Face).
  Chosen over SigLIP 2 for v1 because its weights were obtainable and convertible in the build environment
  (via the Apache-2.0 Weaviate `multi2vec-clip` image on Docker Hub), it is multilingual (Portuguese, Spanish… queries work),
  and it shares one text tower between visual search and transcript/caption semantics. SigLIP 2 B/16 is the planned upgrade:
  swapping it is an `embed` analyser version bump that re-embeds without re-running anything else.
- Shot vector = mean of keyframe vectors (1 per ~3 s, max 5), keyframe vectors kept (`visual_kf`) for zero-shot labels.
- **Text**: v1 reuses the SigLIP text tower for transcript + caption + OCR vectors (`text_embed` analyser, `text` space) rather
  than a separate Qwen3-Embedding service; this keeps CPU installs to one model. Revisit if transcript-semantic search
  quality is the bottleneck in evaluation (eval/README.md).
- **Audio**: CED 527-d posterior per shot stored in the `audio` space for "sounds like this" (`find_similar` modality audio).
