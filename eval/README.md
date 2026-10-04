# Evaluation

Everything here is reproducible with the scripts in this folder. Footage is not committed (see `media/SOURCES.md` for every
clip, its URL and licence); gold labels, scripts and result files are.

**Reference hardware for every number below:** the build machine, a 4 vCPU x86-64 cloud VM with 15 GB RAM and **no GPU**,
shared during measurement with other workloads (load average 10–30 on 4 cores for most of the session). Timings are
therefore pessimistic; quality metrics are unaffected.

## CI gates — `ci_gates.py`

One script, no external footage, exit code 1 when any metric drops below its floor. Everything is generated and seeded,
so a run is byte-for-byte reproducible.

| Gate | What it checks | Floor | Measured |
|---|---|---|---|
| Shot boundaries | 8 synthetic sequences (11,420 frames, 85 transitions): moving `lavfi` patterns (testsrc2, cellauto, life, gradients, scrolling bars) and procedural textured stills (plus two Mandelbrot frames) under a moving virtual camera, some with a moving subject; cuts, dissolves, fades through black/white, wipes, 28 flash decoys. Same detector call and matching as `sbd/evaluate.py` | F1 ≥ 0.85 | **F1 0.937** (P 0.91 / R 0.97) |
| Camera motion | `motion/make_gold.py` moves over 4 procedural 4K stills (40 clips), scored like `motion/evaluate.py` | ≥ 36/40 | **40/40** |
| Parser | the four spec queries in `test_parser_spec_queries` | 4/4 | **4/4** |

Per type: cuts 43/44, dissolves 20/21, fades to black 7/7, fades to white 8/8, wipes 4/5; flash false positives 0/28.
All 8 false positives are second boundaries at the edge of a fade or dissolve ramp, not detections inside shots.
A `lavfi` Mandelbrot zoom is not used as a source: emerging fractal detail reads as a dissolve (F1 0.894 with it) and
deep zooms render too slowly. Runtime: about 2¼ minutes on the 4 vCPU reference machine (under load).

`python ci_gates.py [--json out.json] [--keep DIR]` (from the repo root: `core/.venv/bin/python eval/ci_gates.py`).

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

## Formats, bit depths and colour

`formats/make_matrix.sh` builds 21 camera-style files plus two fake camera-raw files: Sony XAVC HS (HEVC 4:2:2 10-bit HLG,
as an A6700 records) and XAVC S-I (H.264 4:2:2 10-bit All-Intra), HLG and HDR10/PQ, HEVC and H.264 4:4:4 at 10 and 12 bit,
ProRes 422 HQ and 4444 XQ with alpha, DNxHR HQX and 444 (MXF and MOV), XDCAM HD422 and AVCHD interlaced, AV1 and VP9
10-bit, CineForm 12-bit RGB, uncompressed v210, FFV1 16-bit RGB, JPEG 2000 12-bit, MJPEG and DV. Results
(`results/formats-matrix.txt`), with every file run through the whole pipeline:

- **All 21 decodable files analysed with no failed step**; every proxy is browser-playable H.264 4:2:0 8-bit tagged BT.709.
- **Colour:** mean difference from the true test pattern (0–255) is 1–2 for files tagged correctly or stored as RGB or
  JPEG, and about 9 for untagged files that FFmpeg itself encoded with BT.601 maths. We show those as BT.709, as every
  player does, so the mismatch is in the file. HDR (HLG, PQ) is tone-mapped to SDR (BT.2408 reference white,
  soft roll-off): 11–13 from the SDR pattern, against 74–95 before the change, when HDR previews were neither converted
  nor labelled.
- **Camera raw** (BRAW, R3D, ARRIRAW, Canon RAW Light, N-RAW) fails once with a message naming the maker's decoder,
  and works through a configured decoder (tested with a stand-in tool).
- **Damaged files** are reported (`quality.decode_errors`) instead of silently giving a black or glitched preview. The test
  set found one this way: Ubuntu 24.04's libx264 writes 10-bit 4:2:2 streams no FFmpeg can decode, whereas the same
  profile from a current x264 decodes cleanly with FFmpeg 6.1.

## People (face identity)

Demo library, CPU: 134 recognisable faces in 63 files → 67 people (19 s for the whole library). CREMA-D's 10 different
speakers → 10 people. In a visual check of the 16 largest clusters, none mixes two people after the yaw gate (one did
before it). The weakness is over-splitting: the two-person head-pose clip gives 7 clusters, merged in two clicks in
the People view. There is no labelled identity set here, so these are sanity checks rather than accuracy figures.

## Search relevance — `search/`

**Visual descriptions, pooled blind judgments.** 24 tuning queries plus 12 held-out queries (written before the ranking
changes below and judged only afterwards). The top 10 of every variant were pooled into contact sheets with no filenames
or variant labels and graded 0/1/2 by a separate reviewer agent from one keyframe per shot (922 judgments,
`search/judgments.json`). Unjudged results count as irrelevant (1–3% of the final hybrid's top 10).

| Variant | nDCG@10 tuning | P@5 tuning | nDCG@10 held-out | P@5 held-out |
|---|---|---|---|---|
| Hybrid as first built (text-space list, preferences at full weight) | 0.556 | 0.433 | — | — |
| Hybrid, with the text-space list | 0.586 | 0.458 | 0.222 | 0.250 |
| Hybrid, before strong-first ordering | 0.791 | 0.608 | 0.415 | 0.333 |
| **Hybrid (shipped: strong matches first)** | **0.838** | **0.667** | **0.407** | **0.333** |
| Visual vectors only | 0.890 | 0.733 | 0.443 | 0.367 |
| Keywords only (BM25) | 0.529 | 0.408 | 0.292 | 0.250 |
| Hybrid without vocabulary preferences | 0.777 | 0.567 | 0.436 | 0.367 |

**Words people remember, known-item (objective).** 20 four-word phrases from transcripts and 20 from on-screen text, drawn
deterministically from the library; the shot they came from is the target (`search/known_item.py`):

| Variant | Speech MRR@10 / hit@10 | On-screen text MRR@10 / hit@10 |
|---|---|---|
| **Hybrid (shipped)** | **0.92 / 1.00** | **0.90 / 1.00** |
| Hybrid before strong-first ordering | 0.91 / 1.00 | 0.98 / 1.00 |
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

4. **Absolute match strength** (after the fresh UI review): each result carries SigLIP's own sigmoid probability on a
   log scale, raised by exact or partial word evidence from speech and on-screen text, so "strong" means the same thing
   for every query. Strong matches come first (in fused order) for the chosen strictness. Precision of the strong set on
   judged results (`results/search-strength.json`; ranking evaluated with rights hiding off):

   | Strictness | Precision (grade ≥ 1) | Queries with no strong match (of 36) |
   |---|---|---|
   | Loose | 0.53 | 1 |
   | Balanced (default) | 0.64 | 4 |
   | Strict | 0.80 | 11 |

   It improved the tuning set (0.79 → 0.84) and was neutral on held-out (0.415 → 0.407); on-screen text known-item MRR
   fell from 0.98 to 0.90 because partial OCR matches can sit behind strong visual matches. The OCR phrases were also
   re-sampled after the OCR change, so that comparison is approximate.

Visual-only still scores higher on the description sets. Two reasons, and an honest caveat: judges saw the same single
keyframe the visual embedding sees, which favours it; and it cannot find anything by what was said (MRR 0.03), which
hybrid must. The held-out gap is small (0.415 vs 0.443). The held-out set is hard for this 63-file library — several
queries ("dog", "boat on the water", "fireworks") have no relevant shot at all — which is why its absolute numbers are low.

## Throughput and latency

**Search latency at scale** (`../bench/storage_bench.py`, details and the 10 M-shot projection in ADR 002): 1.6 M shots
(3,778 h) on the reference box — median **325 ms**, p95 681 ms with the index loaded from cache (17 s); 276 ms median on
the run that built the index. Filter-only browse 160 ms. Before the benchmark-driven fixes: 775 ms median and 135 s for
a broad filter.

**Analysis throughput** (`throughput.sh`: fresh library, the production server, 3 workers, all 63 demo files — 26 min of
mixed 292p–4K footage): **1.71 hours of footage per hour** on the 4-vCPU CPU-only box (15.3 min wall for 26.2 min of
footage), every CPU-tier analyser enabled. Where the time goes (analyser seconds): proxy transcode 911, OCR 438, SigLIP
embeddings 402, motion 199, keyframes 136, people 132, shots 98, speech 98, visual tags 57, audio 30, the rest < 25.
OCR was 3,140 s before reading the middle keyframe first. A consumer GPU mainly speeds up embeddings and the optional VLM;
proxy transcoding is the largest CPU cost and can use hardware encoders.

## VLM captions (optional GPU tier)

Qwen3.5-2B (Q4, llama.cpp) on this CPU: integration verified end to end — schema-valid JSON first time, vocabulary-
constrained fields, LLM fusion validated without retries — but 490–580 s per shot under load, so not evaluated at scale here.
A consumer GPU is the intended tier for captions; CPU installs use zero-shot labels and template captions.
