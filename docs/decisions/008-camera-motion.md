# 008. Camera motion, capture-speed effects and image quality

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
Editors search by camera language: "slow push-in", "static wide", "handheld follow", "drone reveal",
"locked-off timelapse". For every shot (and sub-shot, ADR 003) we need:

- **Motion primitives**: static, pan L/R, tilt U/D, roll, zoom in/out, dolly in/out, truck,
  pedestal, arc/orbit.
- **Tracking**: the camera follows a subject.
- **Steadiness and rig hypothesis**: tripod, handheld, gimbal/stabilised, drone/aerial, vehicle.
- **Capture-speed effects**: slow motion, timelapse/hyperlapse.
- **Technical quality**: sharpness, exposure, noise, compression blockiness, interlacing, black or
  frozen frames.

These must be deterministic and explainable (each label carries the numbers behind it), run on CPU
faster than real time at reduced resolution, and share the frame decode with shot detection.

**Build environment constraints.** No GPU, 4 shared CPUs (load average 18-27 during testing), 15 GB
RAM. HF and download.pytorch.org are blocked. Reachable: PyPI (`opencv-python-headless` 5.0.0.93,
`opencv-contrib-python`), media.githubusercontent.com (opencv_zoo RAFT ONNX),
raw.githubusercontent.com (BRISQUE model YAMLs), GitHub releases. ffmpeg 6.1 is installed.

## Options considered
### Motion estimation
| Option | Quality | Licence | Hardware | Speed (sandbox, contended) | Maturity / community |
|---|---|---|---|---|---|
| **Sparse KLT tracks (goodFeaturesToTrack + PyrLK, forward-backward check) + RANSAC/USAC similarity, affine or homography** | Robust global motion. Inlier ratio and residuals expose parallax and independent motion | Apache-2.0 (OpenCV) | CPU | **38 fps** at 768x576 (400 points) | Textbook. OpenCV 5.0 |
| OpenCV DIS dense flow (ULTRAFAST/FAST/MEDIUM) | Dense field, so it supports divergence/curl and foreground/background separation | Apache-2.0 | CPU | **89 fps** at 768x576 (ULTRAFAST) | Mature |
| OpenCV Farnebäck | Dense, smoother, slower | Apache-2.0 | CPU | 21 fps at 384x288 | Old but solid |
| RAFT (opencv_zoo ONNX) / SEA-RAFT | Most accurate dense flow | BSD-3-Clause | GPU preferred. 64 MB ONNX | Slow on CPU | Mature research |
| CameraBench fine-tuned Qwen2.5-VL-7B/32B/72B (Lin et al., 2025) | SOTA on CameraBench primitives after SFT; "doubles AP" vs base VLM | Base 7B Apache-2.0 (72B: Qwen licence). Fine-tune and dataset licences **not verified** | GPU, 16 GB+ | Slow (VLM on 8 fps clips) | Research release 2025-04/05 |
| SfM/SLAM (MegaSaM, DROID-SLAM) | Metric camera trajectory | Mixed (DROID-SLAM BSD-3). Check per project | GPU | Slow | Research |
| CoTracker3 point tracks | Excellent long tracks | **CC-BY-NC**. Excluded | GPU | n/a | n/a |

### Image-quality metrics
| Option | What it measures | Licence | Notes |
|---|---|---|---|
| Variance of Laplacian / Tenengrad (global + centre/subject ROI) | Focus and blur | Apache-2.0 (OpenCV) | Must be normalised by resolution and content. ROI vs background separates shallow depth of field from blur |
| Luma histogram stats | Exposure: mean, % clipped ≥ 250 / crushed ≤ 5, dynamic range | n/a | Interpret against `color_transfer` (PQ/HLG) from ffprobe for HDR |
| Immerkær / wavelet-MAD noise sigma (`skimage.restoration.estimate_sigma`) | Sensor noise | BSD-3 | Computed on low-gradient patches |
| 8x8/16x16 boundary blockiness + bits per pixel from ffprobe | Compression damage | n/a | Cheap and deterministic |
| BRISQUE (OpenCV contrib `cv2.quality`) | Overall no-reference IQA | Apache-2.0 (model YAMLs from opencv_contrib) | Works offline. Present in `opencv-contrib-python` 5.0 |
| NIQE | No-reference IQA | scikit-video (BSD) is unmaintained since 2018. **pyiqa is now PolyForm-Noncommercial-1.0.0** (PyPI 0.1.16). Excluded | Re-implement from the paper if wanted |
| CLIP/SigLIP-IQA prompts | Aesthetic and technical quality, zero-shot | Apache-2.0 (SigLIP 2) | Free, since ADR 005 already computes embeddings |
| ffmpeg `idet`, `blackdetect`, `freezedetect`, `cropdetect`, `signalstats` | Interlace/telecine, black, frozen, letterbox, broadcast-range violations | LGPL/GPL ffmpeg CLI (invoked, not linked) | Deterministic. Already a dependency |

## Evidence
- Sandbox micro-benchmark on `vtest.avi` (768x576 static CCTV clip from opencv/samples):
  - DIS ULTRAFAST: 89 fps.
  - Farnebäck at 384x288: 21 fps.
  - KLT + RANSAC partial affine: 38 fps.
  - The fitted affine on this tripod clip is `[[1.0, 0.0, -0.028], [0, 1.0, 0.0]]`, i.e. correctly
    "static" while pedestrians move.
  - The host had a load average of about 20 on 4 vCPUs, so treat these as lower bounds.
- `cv2.quality` is present in `opencv-contrib-python` 5.0.0.93. The BRISQUE model and range files
  are reachable at raw.githubusercontent.com/opencv/opencv_contrib/4.x/modules/quality/samples/.
- CameraBench: https://github.com/sy77777en/CameraBench, paper "Towards Understanding Camera Motions
  in Any Video" (2025). It provides an expert taxonomy and a 1,000+ video test set. Its key finding:
  SfM/SLAM methods (e.g. MegaSaM) handle geometric primitives but miss semantic ones such as tracking
  and arcs, while generic VLMs show the opposite. The fine-tuned Qwen2.5-VL-7B is the strongest open
  model.
- RAFT ONNX: `https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/optical_flow_estimation_raft/optical_flow_estimation_raft_2023aug.onnx`
  (64 MB, reachable).
- pyiqa licence change: PyPI metadata `License-Expression: PolyForm-Noncommercial-1.0.0` (0.1.16,
  2026-07-08). `piq` 0.8.0 is Apache-2.0 but has not been released since 2023.
- CoTracker licence (CC-BY-NC 4.0): https://github.com/facebookresearch/co-tracker.

## Decision
**Deterministic geometric core (CPU, default):**
1. **Decode once** at about 320-480 px wide, analysing 8-12 fps (every n-th frame, n chosen by
   source fps). Share frames with ADR 003.
2. **Track features**: KLT on a 16x16 grid of Shi-Tomasi corners, with forward-backward error < 1 px.
   Mask out boxes of moving objects from ADR 007 (people/vehicles) when they are available.
3. **Fit a model per frame pair** with USAC_MAGSAC: a similarity model gives (tx, ty, s, θ). Also
   fit a homography and keep the inlier ratio and the residual parallax energy. Every 4th pair, run
   DIS ULTRAFAST to get a dense field for divergence, curl and the foreground/background split.
4. **Build time series** smoothed with a Savitzky-Golay filter, then classify segments with
   hysteresis (≥0.5 s):
   - **static**: |t| < 0.2 % of width per frame, |log s| < 0.001, |θ| < 0.05°.
   - **pan / tilt**: sustained tx / ty. Sign gives direction; a rotation-dominant homography
     separates a pan (rotation) from a truck/pedestal (translation with parallax).
   - **zoom vs dolly**: both show scale change. *Zoom* has near-zero parallax (homography fits,
     low residual); *dolly* has radial flow with depth-dependent magnitude (high residual and
     divergence variance).
   - **roll**: sustained θ.
   - **arc/orbit**: opposite-direction translation of foreground and background around a
     stationary subject.
   - **tracking**: a subject box (ADR 007) stays roughly fixed in frame while the background flow
     is large.
   - **steadiness**: spectral energy of the de-trended trajectory. 2-12 Hz jitter → *handheld*;
     smooth with large motion → *gimbal/stabilised or dolly*; near-zero → *tripod/locked-off*.
5. **Rig hypothesis**: drone/aerial and vehicle are semantic. Combine smooth large-scale motion,
   high camera height cues (horizon line, sky ratio, top-down texture) and the VLM answer from
   ADR 004 ("is this aerial footage?"). Output this as a probability, never a hard fact.
6. Every label carries its evidence: mean/peak speeds, scale rate, jitter RMS, inlier ratio.

**Capture-speed effects:**
- Read metadata first. ffprobe `r_frame_rate` / `avg_frame_rate`, `com.android.capture.fps`,
  Apple/QuickTime capture-rate and edit-list (time-mapping) atoms, and the camera maker notes
  readable with exiftool.
- Content heuristics:
  - **slow motion**: high capture fps, or duplicated/interpolated frames (periodic near-zero frame
    differences, optical-flow interpolation artefacts), with implausibly low motion speed for
    detected classes (falling water, walking people).
  - **timelapse/hyperlapse**: large frame-to-frame photometric change (clouds, shadows,
    lighting), "teleporting" people (low KLT survival on foreground) with smooth or static global
    motion.
- Mark these labels `inferred`, unless they come from metadata.

**Image quality:** Laplacian/Tenengrad sharpness (global + subject ROI), exposure stats, noise
sigma, blockiness + bits per pixel, BRISQUE (OpenCV contrib) per keyframe, and ffmpeg `idet`,
`blackdetect` and `freezedetect` per file. These roll up into a 0-1 `technical_quality` score with
its components exposed. NIQE/pyiqa are not used (licence).

**Learned models:** the CameraBench fine-tuned VLM is an optional GPU "second opinion" for
ambiguous segments, after its licence has been verified. Not in the default stack.

## Consequences
- Fully explainable labels with no model weights. The whole analyser is OpenCV + NumPy + ffmpeg.
- The hard classes (dolly vs zoom with little depth variation, arc vs truck, drone vs crane) will
  still have errors. Thresholds need a labelled eval set: CameraBench's public test set is ideal,
  but it is hosted on HF, so mirror it from a normal machine.
- Moving-object masking ties this analyser to ADR 007's detector output (optional; degrades
  gracefully).
- Shot-size and role (ADR 004) can consume the motion evidence instead of guessing from pixels.

## Revisit when
- A permissively licensed, CPU-viable camera-motion model appears (e.g. a CameraBench-style
  fine-tune of an Apache-2.0 2-4B VLM, or a small flow-sequence classifier trained on CameraBench).
- Our eval shows geometric rules below about 0.7 macro-F1 on the semantic classes (tracking, arc,
  aerial).
- A permissive NIQE/BRISQUE successor with video awareness (DOVER-class) is verified Apache/MIT.

## Recommendation for the builder
- `pip install opencv-contrib-python-headless==5.0.0.93 numpy scipy scikit-image`.
  The contrib build is needed for `cv2.quality`. Use the headless contrib wheel, not the mediapipe
  dependency `opencv-contrib-python`.
- BRISQUE files:
  `https://raw.githubusercontent.com/opencv/opencv_contrib/4.x/modules/quality/samples/brisque_model_live.yml`
  and `.../brisque_range_live.yml`.
- Optional dense flow for evaluation only: RAFT ONNX at the media.githubusercontent URL above.
- Synthetic eval clips can be generated locally with ffmpeg:
  - pan/tilt/zoom: `crop` with time expressions, `zoompan`;
  - handheld jitter: `crop` with `random()`-driven offsets;
  - slow-mo: `minterpolate` or `setpts=4*PTS` with frame duplication;
  - timelapse: `select='not(mod(n\,30))'`.

  Use these as unit tests for each primitive before tuning on real footage.

## Outcome (as built, 2026-10-04)

Implemented in `core/metachlorian/media/motion.py` as recommended: KLT feature tracking at 15 fps on 320×180 grey frames,
RANSAC similarity fit per step, **translation measured at the frame centre** (so zooms are not read as pans — this bug was
found by the gold set and fixed), parallax = median residual of near-inliers (dolly/truck vs pan/zoom), subject motion =
share of large residuals, high-frequency jitter after a 0.8 s moving average (handheld vs gimbal vs static). Each movement
term carries a confidence from its margin over the threshold and its direction consistency.

**Gold set** (`eval/motion/make_gold.py`): 40 clips rendered from real 4K stills with exact virtual camera moves (static with
sensor noise, pans, tilts, zooms, band-limited handheld shake, handheld + pan, slow pan) — **40/40 correct** after the fix
(`eval/motion/evaluate.py`, results in `eval/results/motion.json`). Synthetic moves have no parallax or rolling shutter, so
real footage is harder; real-footage behaviour is covered by the content gold set (`eval/content`). Drone/aerial is not
measurable from flow alone and is fused from zero-shot and VLM evidence (ADR 004/005).

Speed effects: slow motion and timelapse are not yet measured deterministically (VLM-only); metadata-based detection
(capture fps vs playback fps) is the next step.
