# Evaluation

Everything here is reproducible with the scripts in this folder. Footage is not committed (see `media/SOURCES.md` for every
clip, its URL and licence); gold labels, scripts and result files are.

**Reference hardware for every number below:** the build machine, a 4 vCPU x86-64 cloud VM with 15 GB RAM and **no GPU**,
shared during measurement with other workloads (load average 10–30 on 4 cores for most of the session). Timings are
therefore pessimistic; quality metrics are unaffected.

## Shot boundaries — `sbd/`

Real CC-BY footage segments joined with exactly known transitions, plus single-frame flash decoys.

| Detector | Tuning F1 (81 transitions) | Held-out F1 (21) | Held-out P / R | Flash false positives |
|---|---|---|---|---|
| **Metachlorian** | **0.921** | **0.870** | 0.80 / 0.95 | 1 / 0 |
| PySceneDetect Adaptive | 0.707 | 0.634 | 0.65 / 0.62 | 6 / 2 |
| PySceneDetect Content | 0.716 | 0.683 | 0.70 / 0.67 | 8 / 2 |
| PySceneDetect Histogram | 0.689 | 0.656 | 0.50 / 0.95 | 8 / 2 |

Per type (tuning): cuts 48/48, dissolves 15/19, fades to black 5/5, fades to white 2/2, wipes 6/7.
`python sbd/make_gold.py <clips> <out> 8 7` then `python sbd/evaluate.py <out>`. Results: `results/sbd-*.json`.

## Camera motion — `motion/`

40 clips rendered from real 4K stills with exact virtual camera moves (static, pan ×2, tilt ×2, zoom ×2, handheld,
handheld + pan, slow pan): **40/40 correct** (`results/motion.json`). A centring bug (zooms read as pans) was found by this
set and fixed. Synthetic moves have no parallax or rolling shutter, so real footage is harder.

## Content labels — `content/`

97 shots from 63 files labelled by visual inspection of 4 keyframes each (`gold.json`), plus a **held-out** set of 28
different shots labelled *after* tuning (`gold-heldout.json`). CPU tier = zero-shot SigLIP labels + measured signals, no VLM.

| Signal | Tuning set (before → after tuning) | Held-out |
|---|---|---|
| Interior / exterior | 13% → 88% | 81% |
| Setting, top-1 (specific term, broader/narrower accepted) | 52% → 69% | 76% |
| Setting, any of top terms | 69% → 84% | 84% |
| Time of day (day / golden / dusk / night) | 69% → 93% | 93% |
| People count bucket (0 / 1 / 2–5 / 6+) | 78% | 80% |
| Shot size exact / within one step | 35% / 79% | 45% / 91% |
| Aerial (drone) recall | 4 of 8 | 2 of 3 |

Tuning was structural (a dedicated indoor/outdoor decision instead of one term among 30, coarse time-of-day classes,
specific prompts for over-generic settings), not threshold fitting, and the held-out set confirms it generalises — but both
sets come from the same 63-file library, so treat them as indicative.

**Fused records** (what search and agents actually see, after fusion with measured signals) — `content/evaluate.py`,
`results/content-fused*.json`:

| Signal | Tuning set | Held-out |
|---|---|---|
| Interior / exterior | 88% | 81% |
| Setting top-1 / any kept term | 69% / 79% | 76% / 80% |
| Time of day | 93% | 93% |
| People count bucket | 78% | 80% |
| On-screen text present | 92% | 96% |
| Shot size exact / within one step | 35% / 79% | 45% / 91% |
| Aerial precision / recall | 0.63 / 0.63 | 0.75 / 1.00 |
| Blank / unusable frames flagged | 3 / 3 | — |

The first fused run scored setting top-1 at 59%, below the raw labels: fusion was dropping zero-shot terms below 0.55
confidence and counting repeated votes from one source as independent evidence. Both were fixed (fusion 1.3.0, with a
regression test), and the fused record now carries the full evidence with honest confidences.

Shot size is the weakest signal on CPU (exact match 35–45%): it comes from face and person box sizes, which cannot tell a
medium shot from a medium close-up reliably. The VLM tier is the intended fix (see below).

## Speech — `asr/`

Parakeet TDT 0.6B v3 (int8, CPU) against the human subtitles that ship with the clips:

| Clip | WER |
|---|---|
| Scott Ko talking head (clean speech) | 1.3% |
| CREMA-D, 10 speakers | 5.3% |
| Meridian (film dialogue, music) | 18.1% |
| Tears of Steel (film, effects) | 25.0% |
| **Overall (≈480 reference words)** | **15%** |

Subtitle references paraphrase and omit lines (e.g. "We have main engine start…" is spoken but not subtitled), so film
WER overstates errors. VAD settings were tuned on this set (19% → 15%). Language identification: 4/4 files correct (all English).
Diarisation counts are approximate (TitaNet-small on 2 s utterances under-clusters; films over-cluster) — known weakness.

## Search relevance — `search/`

**Visual descriptions, pooled blind judgments.** 24 tuning queries plus 12 held-out queries (written before the ranking
changes below and judged only afterwards). The top 10 of every variant were pooled into contact sheets with no filenames
or variant labels and graded 0/1/2 by a separate reviewer agent from one keyframe per shot (922 judgments,
`search/judgments.json`). Unjudged results count as irrelevant (1–3% of the final hybrid's top 10).

| Variant | nDCG@10 tuning | P@5 tuning | nDCG@10 held-out | P@5 held-out |
|---|---|---|---|---|
| Hybrid as first built (text-space list, preferences at full weight) | 0.556 | 0.433 | — | — |
| Hybrid, with the text-space list | 0.586 | 0.458 | 0.222 | 0.250 |
| **Hybrid (shipped)** | **0.791** | **0.608** | **0.415** | **0.333** |
| Visual vectors only | 0.890 | 0.733 | 0.443 | 0.367 |
| Keywords only (BM25) | 0.529 | 0.408 | 0.292 | 0.250 |
| Hybrid without vocabulary preferences | 0.777 | 0.567 | 0.436 | 0.367 |

**Words people remember, known-item (objective).** 20 four-word phrases from transcripts and 20 from on-screen text, drawn
deterministically from the library; the shot they came from is the target (`search/known_item.py`):

| Variant | Speech MRR@10 / hit@10 | On-screen text MRR@10 / hit@10 |
|---|---|---|
| **Hybrid (shipped)** | **0.91 / 1.00** | **0.98 / 1.00** |
| Hybrid before the exact-words list | 0.55 / 1.00 | 0.70 / 0.85 |
| Visual vectors only | 0.03 / 0.15 | 0.46 / 0.65 |
| Keywords only | 1.00 / 1.00 | 0.97 / 1.00 |

What changed, and why:
1. The SigLIP text-tower list (query vs transcript/caption embeddings) was dropped from fusion; it is not a sentence
   embedder and was the largest source of off-topic results (0.58 → 0.73 on tuning, 0.22 → 0.37 held-out).
2. Vocabulary preferences were cut from weight 1.1 to 0.3: the list is ordered by label confidence, not relevance to the
   whole query, and CPU-tier labels are ~70–90% accurate (0.73 → 0.79 tuning, 0.37 → 0.41 held-out).
3. A new "exact words" list — every query word said, shown on screen, or in the place or file name — carries the
   strongest weight, so remembered lines and on-screen text rank first while descriptive queries are unaffected.

Visual-only still scores higher on the description sets. Two reasons, and an honest caveat: judges saw the same single
keyframe the visual embedding sees, which favours it; and it cannot find anything by what was said (MRR 0.03), which
hybrid must. The held-out gap is small (0.415 vs 0.443). The held-out set is hard for this 63-file library — several
queries ("dog", "boat on the water", "fireworks") have no relevant shot at all — which is why its absolute numbers are low.

## Throughput and latency

**Search latency at scale** (`../bench/storage_bench.py`, details and the 10 M-shot projection in ADR 002): 1.6 M shots
(3,778 h) on the reference box — median **325 ms**, p95 681 ms with the index loaded from cache (17 s); 276 ms median on
the run that built the index. Filter-only browse 160 ms. Before the benchmark-driven fixes: 775 ms median and 135 s for
a broad filter.

**Analysis throughput** — measured with `throughput.sh` (fresh library, production server, 3 workers); result to follow.

## VLM captions (optional GPU tier)

Qwen3.5-2B (Q4, llama.cpp) on this CPU: integration verified end to end — schema-valid JSON first time, vocabulary-
constrained fields, LLM fusion validated without retries — but 490–580 s per shot under load, so not evaluated at scale here.
A consumer GPU is the intended tier for captions; CPU installs use zero-shot labels and template captions.
