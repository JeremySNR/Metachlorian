# 016. Hybrid ranking and query understanding

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
One search request fans out to several retrievers, all under the same structured filters (002):
- **keyword**: BM25 over transcript, OCR, captions and tags;
- **visual vector**: text-to-image embedding against shot keyframes;
- **text vector**: semantic search over transcript and captions.

Their scores are not comparable. FTS5 `bm25()` is unbounded and negative-is-better, cosine similarities from different models have different distributions, and one retriever may return nothing.

We need two things:
- **(a) a fusion method;**
- **(b) an optional reranking stage.**

Both must add **≤ ~100 ms on CPU**. We also need **(c) natural-language query parsing** into structured filters. For example, "wide shots of Sarah outdoors at night from the 2024 Lisbon shoot" becomes `{person: Sarah, shot_size: wide, setting: exterior, time_of_day: night, project: "Lisbon 2024"}`.

Constraints:
- Licences must be OSI or commercially usable.
- In the build environment, **Hugging Face is blocked**, so model weights must come from PyPI or npm packages or GitHub release assets, or the feature must be optional.
- No GPU, 4 CPUs.
- `eval/` will hold relevance judgments.

## Options considered
### Fusion
| Option | Quality | Licence | Hardware | Speed | Maturity | Notes |
|---|---|---|---|---|---|---|
| **Reciprocal Rank Fusion (RRF)** `Σ w_i/(k+rank_i)`, k≈60 | Robust without tuning. Ignores score magnitude. A tuned RRF "generalizes poorly" out of domain, and it is sensitive to k ([Bruch et al., TOIS 2023](https://dl.acm.org/doi/10.1145/3596512), [arXiv](https://arxiv.org/abs/2210.11934)). | n/a | Trivial | <1 ms | Default in LanceDB ([docs](https://docs.lancedb.com/search/hybrid-search)) and available in OpenSearch 3.7 ([blog](https://opensearch.org/blog/explore-opensearch-3-7/)) | Needs no labels. Handles retrievers that return nothing. |
| **Convex combination (weighted score fusion)** of normalised scores (min-max, z-score or theoretical bounds) | **Beats RRF in- and out-of-domain once α is tuned, and is sample-efficient** (Bruch et al.) | n/a | Trivial | <1 ms | Common (OpenSearch normalisation processor) | Needs a small labelled set and per-retriever normalisation. Brittle when a retriever's score distribution shifts, e.g. after a model upgrade. |
| Learned ranker (LambdaMART with LightGBM/XGBoost) over features: BM25, cosines, recency, shot length, face match, etc. | Best once there are thousands of judgments or click logs | MIT / Apache-2.0 | CPU, tiny | <5 ms for 200 candidates | Mature | Needs training data we do not have yet. Risk of overfitting a small `eval/`. |

### Reranking (text fields of top-N candidates: caption + transcript snippet + tags)
| Model | Params | Licence | CPU fit for ≤100 ms on 30-50 pairs | Notes |
|---|---|---|---|---|
| **Ettin reranker 17M / 32M / 68M** | 17.6M / 32.8M / 68.6M | **Apache-2.0** ([HF blog](https://huggingface.co/blog/ettin-reranker), [blog source on GitHub](https://github.com/huggingface/blog/blob/main/ettin-reranker.md)) | 17M and 32M likely fit with ONNX int8 (to be measured) | Newest small cross-encoders. 17M beats ms-marco-MiniLM-L12 by +0.051 nDCG@10 with half the parameters. Check the training-data terms on the dataset card. |
| ms-marco-MiniLM-L6/L12 (sentence-transformers) via FlashRank or ONNX | 22M / 33M | Apache-2.0 weights. **MS MARCO data is "for non-commercial research purposes only"** ([microsoft/msmarco](https://github.com/microsoft/msmarco)), so the derived-weights status is unclear. Packaged by [FlashRank](https://github.com/PrithivirajDamodaran/FlashRank) (Apache-2.0). | Yes: ~15-30 ms reported for 16 candidates on CPU ([rag-reranking-benchmarks](https://github.com/clouatre-labs/rag-reranking-benchmarks)) | Treat as a data-provenance risk |
| mxbai-rerank-xsmall-v1 | 70.8M (DeBERTa-v3) | Apache-2.0 ([repo](https://github.com/mixedbread-ai/mxbai-rerank)) | Borderline | Good quality per parameter |
| mxbai-rerank-base/large-v2 | 0.5B / 1.5B (Qwen-2.5) | Apache-2.0 | **No.** Mixedbread reports ~3.5 pairs/s on an i7-13700K for base-v2 ([blog](https://www.mixedbread.com/blog/mxbai-rerank-v2)). | GPU-only for us |
| bge-reranker-base / v2-m3 | 278M / 568M | MIT / Apache-2.0 ([BGE docs](https://bge-model.com/bge/bge_reranker_v2.html)) | No (v2-m3), borderline (base) | Strong multilingual quality |
| jina-reranker v2 / v3 / v3.5, jina-colbert-v2 | — | **CC BY-NC 4.0 licence trap**. Commercial use needs a paid licence, sold by Elastic as "Jina On-Prem" ([model page](https://jina.ai/models/jina-reranker-v3/), [v2 page](https://jina.ai/models/jina-reranker-v2-base-multilingual/)). | — | **Excluded** |
| Late interaction (ColBERT): answerai-colbert-small-v1 via PyLate | 33M | Apache-2.0 model, MIT library ([PyLate](https://github.com/lightonai/pylate)) | Query encode ~10 ms. MaxSim over stored token vectors is fast. | Storage ~20-36 B per token even compressed ([ColBERTv2](https://arxiv.org/abs/2112.01488)). At 10 M shots × ~100 tokens that is **tens of GB**. As a reranker it can encode candidates on the fly, which costs about the same as a cross-encoder. |

### Natural-language query parsing
| Option | Quality | Licence | Speed on CPU | Notes |
|---|---|---|---|---|
| **Rule/grammar parser** with a library-driven vocabulary: people, projects, locations and tag names read from the DB, plus enumerated shot sizes and times of day, and dates through `dateparser` (BSD-3) | High precision on known facets. Explainable. | Ours + BSD/MIT (Lark MIT) | **< 5 ms** | Deterministic, so it is testable in `eval/`. Unparsed residue goes to keyword and vector search. |
| Local LLM with JSON-schema constrained decoding (llama.cpp GBNF / `json_schema_to_grammar`, Outlines, XGrammar) | Handles paraphrase and negation | MIT / Apache-2.0 runtimes. Model licences vary. | Grammar masking adds little on CPU ([llama.cpp server docs](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)). **Generating ~40 JSON tokens with a 0.5-1.5B model on 4 cores is roughly 0.5-2 s** (estimate, to be measured), which breaks the 100 ms budget. | Weights usually come from Hugging Face, which is blocked in the build environment |
| Hosted LLM (user-configured, as in Cutawan) | Best | Provider terms | Network latency of 300 ms or more | Sends queries off-box. Opt-in only. |
| Let the agent do it (MCP) | n/a | n/a | 0 ms | MCP tools take **structured filters directly**, so agents never need our NL parser |

## Evidence
- Bruch et al. (ACM TOIS 2023) show that convex combination beats RRF when tuned on a small sample, and that RRF is sensitive to `k`. With no labels yet, RRF is the safe starting point. `eval/` will provide the labels to move on from it.
- Small Apache-2.0 cross-encoders (Ettin 17M/32M) now beat the classic MS MARCO MiniLM rerankers at similar or lower cost. They avoid both the MS MARCO data-licence ambiguity and the Jina CC BY-NC trap.
- Mixedbread's own numbers put 0.5B+ LLM rerankers at a few pairs per second on CPU, far outside budget. bge-reranker-v2-m3 (568M) is the same.
- Storing ColBERT token vectors at our scale costs tens of GB, which does not justify the gain over a cross-encoder applied to a top-50.
- Shot search is multimodal. A text cross-encoder can only judge text fields, so it must not demote shots that were found purely visually and have no transcript.

## Decision
1. **Candidate generation:** each retriever returns its top 200 under the same filters.
2. **Fusion v1: weighted RRF**, k=60, with per-retriever weights (default keyword 1.0, visual 1.0, text-semantic 0.8). Weights rise when the parser finds quoted phrases (keyword) or visual-only intent. Results are de-duplicated by shot and keep **per-retriever contributions** so the UI and MCP can explain matches.
3. **Fusion v2 (gated on `eval/`):** a convex combination with per-retriever z-score normalisation and α tuned on the judgments. Adopt it only if it beats RRF on nDCG@10 by ≥ 0.02 on a held-out split. Consider a LambdaMART ranker after we have more than ~2k judged queries.
4. **Optional rerank:** an **Ettin-reranker-32M (fallback 17M) cross-encoder, exported to ONNX int8, scoring the top 40.** It runs only for queries with textual intent, with a hard budget of 80 ms that falls back to the fused order on timeout. The final score blends `0.7·rerank + 0.3·fused`, so visual-only hits are not wiped out. It is **off by default** until weights are mirrored as a GitHub release asset with LICENSE/NOTICE (Apache-2.0 allows redistribution), because Hugging Face is unreachable in the build environment.
5. **Query understanding:** a deterministic grammar/vocabulary parser on the hot path. It produces editable filter "chips" and a residual text query. LLM parsing (local llama.cpp with a JSON schema, or a user-configured hosted model) is opt-in, runs asynchronously as a "did you mean these filters?" suggestion, and is never needed for MCP clients.

## Consequences
- Works on day one with no labels, no model downloads and less than 5 ms of fusion overhead.
- Explainable ranking (which retriever contributed what) carries through to the UI and MCP.
- We maintain a facet vocabulary and grammar, and must test them against real phrasing in `eval/`.
- Tuning weights or switching to a convex combination needs a judgment set. Analyser or model upgrades call for re-tuning, because score distributions shift.
- The reranker adds a model artefact to the release pipeline, along with its licence review.

## Revisit when
- `eval/` has ≥ 200 judged queries: run the RRF vs convex-combination comparison. At ≥ 2k, try LambdaMART.
- Reranker p95 exceeds 100 ms on reference hardware, or it fails to add ≥ 0.02 nDCG@10.
- A permissively licensed multimodal (image-text) reranker small enough for CPU appears, so visual hits can be reranked too.
- A small (<1B) permissively licensed local model parses filters in < 150 ms on CPU, which would allow LLM parsing on the hot path.
- Jina, BGE or Mixedbread change licences, or the provenance of Ettin's training data turns out to be restrictive.

## Outcome (as built, 2026-10-04)

Implemented in `core/metachlorian/search/engine.py`: weighted RRF (k = 60) over up to five lists — visual vectors (SigLIP
text→image), text vectors (transcript/caption semantics), FTS5 BM25 (column weights caption 1.0, transcript 0.8, OCR 0.9,
tags 1.2, place 1.6, filename 0.5), vocabulary-term preferences (per-term top-k by confidence via an index), and
query-by-example — plus small priors for preferred people count and quality, a usability penalty, rights filtering, and
per-result explanations built from each retriever's contribution. Query parsing is rule- and vocabulary-based
(`search/parse.py`, < 5 ms). No cross-encoder reranker in v1. Relevance numbers per variant are in `eval/README.md`.
