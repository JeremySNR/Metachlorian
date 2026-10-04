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
sets come from the same 63-file library, so treat them as indicative. Fused-record accuracy (after fusion, with crowd and
aerial evidence) is reported by `content/evaluate.py` in `results/content-fused.json`.

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
WER overstates errors. VAD settings were tuned on this set (19% → 15%). Language identification: 5/5 English files correct.
Diarisation counts are approximate (TitaNet-small on 2 s utterances under-clusters; films over-cluster) — known weakness.

## Search relevance — `search/`

Pending: pooled judgments for 24 queries over the demo library comparing hybrid vs visual-only vs keyword-only vs no
vocabulary preferences (`search/relevance.py`).

## Throughput and latency

Pending: hours of footage per hour on the reference box (`metachlorian status` → `throughput`), and the storage benchmark
(`../bench/storage_bench.py`) at library scale.

## VLM captions (optional GPU tier)

Qwen3.5-2B (Q4, llama.cpp) on this CPU: integration verified end to end — schema-valid JSON first time, vocabulary-
constrained fields, LLM fusion validated without retries — but 490–580 s per shot under load, so not evaluated at scale here.
A consumer GPU is the intended tier for captions; CPU installs use zero-shot labels and template captions.
