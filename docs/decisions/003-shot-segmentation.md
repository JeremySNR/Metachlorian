# 003. Shot segmentation (cuts, transitions, long-take sub-segments)

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
Every later analyser in Metachlorian (captions, camera motion, embeddings, OCR) works per shot, so the
segmenter fixes the unit of search. It has to find hard cuts and gradual transitions (fades, dissolves,
wipes) in very different footage: broadcast, phone vlogs, drone rushes and screen recordings. It must
also split long single takes (a 4-minute gimbal walk, a 30-minute interview) into segments that make
sense on their own, because a single 30-minute "shot" is useless as a search result.

Product constraints: Apache-2.0 project, so all code and weights must allow commercial use. It must run
on CPU, with a GPU optional. Inputs are often variable frame rate (VFR) phone footage.

**Build environment constraints.** The build machine has no GPU, 4 CPUs and 15 GB RAM, and is shared:
load averages of 18-27 were seen during this research, so any timings taken here are upper bounds.
Hugging Face, ollama.com and download.pytorch.org are blocked. PyPI, GitHub release downloads,
raw.githubusercontent.com, media.githubusercontent.com (Git LFS), storage.googleapis.com, Docker Hub
and ghcr.io are reachable. Google Drive and Baidu Pan links are not usable from here. The default
segmenter must therefore be testable without Hugging Face.

## Options considered
| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| PySceneDetect `AdaptiveDetector` | Best classical option. Hard-cut F1: 91.6 on BBC, 73.9 on AutoShot, 55.8 on ClipShots | BSD-3-Clause | CPU | About 36 s per BBC clip (≈ decode-bound) | v0.7.1 (2026-07-21). VFR-correct since 0.7 | Active, single main maintainer, popular |
| PySceneDetect `ContentDetector` | Hard-cut F1: 86.7 BBC, 69.3 AutoShot, 55.8 ClipShots | BSD-3 | CPU | Similar | Mature | Same |
| PySceneDetect `HashDetector` / `HistogramDetector` | Lower on cuts (F1 83.1 and 80.0 on BBC). Histogram is best on **fades**: F1 75.3 on ClipShots fades, vs 24 for Adaptive | BSD-3 | CPU | Fastest (22-26 s per BBC clip) | Mature | Same |
| PySceneDetect `ThresholdDetector` | Only finds fades to and from black | BSD-3 | CPU | Fastest | Mature | Same |
| TransNetV2 (soCzech) | Learned 3D-CNN. Strong on cuts and gradual transitions; the reference baseline in every SBD paper | MIT. Weights (30 MB) are bundled in the `transnetv2-pytorch` 1.0.5 wheel on PyPI | CPU works, GPU better | Light (~30 MB of weights, 48x27 input frames) | 2020 model, still the standard baseline | Original repo is quiet. The PyPI port was updated in 2025 |
| AutoShot (CVPR-W 2023) | +4.2 % F1 over TransNetV2 on SHOT (short videos). Range F1 0.814 on OmniShotCutBench, the same as TransNetV2 | MIT code. Weights only on Baidu Pan / Google Drive | GPU preferred | Similar to TransNetV2 | Research code | Dormant |
| OmniShotCut (UVA, Apr 2026) | New state of the art. On OmniShotCutBench: Range F1 0.883 (vs 0.814), transition IoU 0.632 (vs 0.19-0.25), sudden-jump accuracy 0.761 (vs 0.26-0.46). Also labels the transition type | MIT (code). Weights are on HF only | PyTorch + CUDA. 52.8 M parameters (v1.5) | Not published | 5 months old. pip package and Gradio demo exist | ~317 stars. Active, with an MLX port |
| PERSIST (Aug 2026 preprint) | Cuts false positives from flashes, text overlays and archival footage by 33-80 %. Roughly halves TransNetV2's pseudo-event false positives | Code on GitHub. Licence not yet verified | Not stated | n/a | Preprint | New |
| Fassold 2025 (motion field + NCC) | Hard cuts and short dissolves, robust to flashes. Also detects interlace/pulldown | Paper only | CPU | Reported 4x faster than real time | Paper | n/a |

## Evidence
- PySceneDetect's own TRECVID-style benchmark (hard-cut F1 at 1-frame tolerance, v0.7) is the source
  of every PySceneDetect number above. The parameter sweep found the best mean F1 at
  `AdaptiveDetector(adaptive_threshold=3.5, window_width=3, min_scene_len=0.6s)` = 76.3, versus 73.4
  for the best ContentDetector setting
  (https://github.com/Breakthrough/PySceneDetect/blob/main/benchmark/README.md).
- PySceneDetect 0.7 reworked timestamps for VFR and removed deprecated APIs. 0.7.1 (2026-07-21) added
  concatenation and backend fixes (https://www.scenedetect.com/changelog/,
  https://github.com/Breakthrough/PySceneDetect/releases). PyPI: `scenedetect 0.7.1`, BSD-3-Clause.
- OmniShotCut repo and benchmark (MIT, weights on HF, v1.5 has 52.8 M parameters):
  https://github.com/UVA-Computer-Vision-Lab/OmniShotCut. Paper with comparison tables:
  https://arxiv.org/abs/2604.24762 (table also at
  https://www.sota2.com/research/sota/shot-boundary-detection-on-omnishotcutbench).
- AutoShot: https://github.com/wentaozhu/AutoShot (MIT. Weights linked from Baidu Pan / Google Drive).
  Paper: https://arxiv.org/abs/2304.06116.
- TransNetV2: https://github.com/soCzech/TransNetV2 (MIT). The PyPI wheel `transnetv2-pytorch==1.0.5`
  contains `transnetv2-pytorch-weights.pth` (30.5 MB), checked by downloading the wheel in the sandbox.
- PERSIST: https://arxiv.org/abs/2608.29287, code https://github.com/linty5/PERSIST.
- Fassold, "Faster than real-time detection of shot boundaries...": https://arxiv.org/abs/2502.09202.
- Long-take segmentation tools: `ruptures` 1.1.10 (BSD-2-Clause, change-point detection, PyPI).
  `imagehash` 4.3.2 (BSD-2).
- No benchmark has been run in `eval/` yet. See "Recommendation for the builder".

## Decision
1. **Default (CPU, always on): PySceneDetect 0.7.x driving a small "own detector" ensemble.**
   - Hard cuts: `AdaptiveDetector` with the sweep-optimal parameters above, as the primary signal.
   - Fades and dissolves: `HistogramDetector` plus `ThresholdDetector` (fade to black). Their
     candidates are kept only when a slow ramp in the content score spans at least 4 frames, which
     separates a dissolve from a cut.
   - Flash suppression: reject a candidate if the frames at t-k and t+k are near-identical
     (perceptual hash distance below a threshold). This is the PERSIST "return-to-trend" idea, done
     cheaply.
   - All three run in one decode pass at reduced resolution (e.g. 320 px wide). Decoding is the
     bottleneck, so share frames with the camera-motion and quality analysers (ADR 008).
2. **Optional "accurate" tier: TransNetV2 exported to ONNX** (MIT, 30 MB). It is fused with the
   classical candidates: a cut needs either TransNetV2 p > 0.5 or agreement from two classical
   detectors. This is testable here, because the weights come from PyPI.
3. **Watch / GPU tier: OmniShotCut.** It is the clear quality leader on transitions and on
   "sudden jump" (jump-cut) detection, and it is MIT licensed. It is not the default because it is
   CUDA-oriented, its weights are only on Hugging Face, and it is five months old. Offer it as a
   plug-in once an ONNX export exists and our own eval confirms the gains.
4. **Long single takes are split into sub-shots** (`segment_kind = "subshot"`, with a
   `parent_shot_id`). A boundary is placed where any of these fire:
   - (a) the camera-motion class changes and stays changed for at least 1.5 s (from ADR 008, with
     hysteresis);
   - (b) semantic drift: SigLIP/CLIP embeddings are sampled at 1 fps (ADR 005), and either the
     cosine distance to the running segment centroid exceeds a tuned threshold, or `ruptures` (PELT,
     cosine cost) finds a change point;
   - (c) speech structure: a speaker turn, or a sentence end followed by a pause of at least 0.7 s
     (ADR 006);
   - (d) a hard cap of 30 s (configurable), snapped to the nearest low-motion, high-sharpness frame.
   Sub-shots never go below 2 s. Each segment keeps a representative keyframe: the sharpest frame
   near the temporal centre.

## Consequences
- The default stack needs no model download. It is deterministic, BSD/MIT licensed, and works on VFR
  footage.
- Classical detectors under-detect dissolves and jump cuts (ClipShots fades F1 is 24-41 for
  content-based detectors). The fusion rules and the optional TransNetV2 make up part of that gap.
  OmniShotCut is the path to transition typing.
- Sub-shot splitting depends on the camera-motion, embedding and ASR outputs, so segmentation becomes
  a two-pass process: cut detection first, then sub-shot refinement after the analysers. The data
  model must allow segment boundaries to be revised.
- Thresholds must be tuned on our own eval set. PySceneDetect's defaults are not optimal: its own
  sweep shows the best parameters differ from the v0.7 defaults.

## Revisit when
- OmniShotCut (or a successor) ships ONNX weights or a CPU path, and beats our fused default by more
  than 5 F1 points on our eval set.
- The PERSIST code licence is confirmed permissive, and it shows a CPU-friendly runtime.
- PySceneDetect adds a learned detector or a fade/dissolve
  detector that scores better.
- Users report over-splitting or under-splitting of long takes, i.e. the median sub-shot length
  falls outside 4-20 s on real libraries.

## Recommendation for the builder
- `pip install scenedetect==0.7.1 av` (PyAV backend, BSD-3), both from PyPI. Use the
  `AdaptiveDetector(adaptive_threshold=3.5, window_width=3, min_scene_len=0.6s)` defaults above.
- TransNetV2 weights, testable here: `pip download transnetv2-pytorch==1.0.5 --no-deps`. The wheel
  contains `transnetv2_pytorch/transnetv2-pytorch-weights.pth`. Export to ONNX once with `torch`
  (CPU wheel from PyPI, `torch==2.14.1`), then publish the `.onnx` as a Metachlorian GitHub release
  asset, so the runtime only needs `onnxruntime`.
- Build a small eval: the BBC Planet Earth annotations are on Zenodo
  (https://zenodo.org/records/14873790). Zenodo was not reachable from this sandbox, so mirror the
  annotations into `eval/` once from a normal machine. Add synthetic cases with `ffmpeg`
  (`xfade=transition=fade|dissolve|wipeleft`) to measure transition recall locally.
- Do not use the AutoShot or OmniShotCut weights in the default path: their hosts (Baidu / Google
  Drive / HF) are unreachable here.

## Outcome (as built, 2026-10-04) — supersedes the Decision above where they differ

We benchmarked before committing, as the process requires, and the result changed the default.

**Gold set** (`eval/sbd/make_gold.py`): real CC-BY footage segments joined with exactly known transitions — hard cuts,
dissolves (10–30 frames), fades through black and white, wipes — with single-frame camera-flash decoys inserted inside shots.
8 tuning sequences (81 transitions) and a held-out set with a different seed (21 transitions).

| Detector | Tuning F1 | Held-out F1 | Held-out precision | Held-out recall | Dissolves found (tuning) | Flash false positives |
|---|---|---|---|---|---|---|
| **Metachlorian detector** (`media/shots.py`) | **0.921** | **0.870** | 0.80 | 0.95 | 15/19 | 1 |
| PySceneDetect AdaptiveDetector | 0.707 | 0.634 | 0.65 | 0.62 | 1/19 | 6 |
| PySceneDetect ContentDetector | 0.716 | 0.683 | 0.70 | 0.67 | 2/19 | 8 |
| PySceneDetect HistogramDetector | 0.689 | 0.656 | 0.50 | 0.95 | 17/19 | 8 |

(`python eval/sbd/evaluate.py <gold_dir>`; results in `eval/results/`.) All four process 550–850 fps at 96×54 on the
build machine's CPU.

**Decision as built:** the default is our own deterministic detector, which combines an adaptive ratio test on a
colour-histogram + pixel-difference score (hard cuts), a blend test over a ±0.4 s window (dissolves and wipes), dark/bright
run detection with ramps (fades), and flash rejection when the content after a spike matches the content before it.
PySceneDetect stays as the benchmark baseline. Long takes are split by content drift from the segment start, with a
configurable cap (20 s) snapped to the calmest frame. TransNetV2/OmniShotCut remain the optional accurate tier for a GPU
build (not yet integrated).

**Known weaknesses seen on real footage**: very fast-cut black-and-white music video with heavy smoke and strobing
(`ugc_MusicVideo_1080P-2b2b`) where some cuts between similar-looking frames are missed; source footage with intrinsic fades
is (correctly) segmented at those fades. Revisit with TransNetV2 when a GPU tier is available.
