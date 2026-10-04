# 006. Speech and audio (ASR with word timings, diarisation, audio events, loudness)

- Status: proposed
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
For every shot we want five things:
- a transcript with word- or token-level timestamps, so quotes can be found and shots trimmed to
  words;
- the spoken language;
- speaker turns (who spoke when, anonymous speaker IDs across a file);
- audio event tags ("applause", "siren", "music", "wind noise");
- loudness and technical audio quality (integrated LUFS, LRA, true peak, clipping, silence).

It must run on CPU with light dependencies (ONNX Runtime first, no PyTorch at inference),
and it must cover non-English footage. Every weight must allow commercial use.

**Build environment constraints.** No GPU, 4 shared CPUs (load average 18-27 during testing), 15 GB
RAM. Hugging Face is blocked, which rules out the default model sources of faster-whisper,
whisper.cpp and pyannote. Reachable: PyPI, GitHub releases (including all k2-fsa/sherpa-onnx model
assets), storage.googleapis.com, Docker Hub and ghcr.io. Zenodo is not reachable, so PANNs weights
cannot be fetched here.

## Options considered
### ASR
| Option | Quality | Licence | Hardware | Speed | Timestamps | Maturity / community |
|---|---|---|---|---|---|---|
| **NVIDIA Parakeet-TDT-0.6B-v3** (via sherpa-onnx int8) | Open ASR Leaderboard avg WER 6.34 % (English). 25 European languages with auto language ID | **CC-BY-4.0** (attribution required; commercial OK) | CPU fine (int8 ≈ 640 MB) | RTFx 3,332 on GPU (leaderboard). Community CPU int8 reports are ≈12-18x real time | Token timestamps from the transducer, merged into words | NeMo-backed. sherpa-onnx support since 2025 |
| Parakeet-TDT-0.6B-v2 | English only, slightly better English WER | CC-BY-4.0 | CPU | Same | Tokens | Same |
| Whisper large-v3 / large-v3-turbo / distil-large-v3.5 | WER ≈7.4 % (v3), 7.75 % (turbo). **99 languages**, robust to noise. Known to hallucinate on silence and music | MIT | GPU preferred. Turbo or distil on CPU | Turbo is ~5-8x faster than v3 | sherpa-onnx: segment timestamps. Token timestamps only with ONNX exports that include attention outputs. faster-whisper: word timestamps via DTW | Very mature. faster-whisper 1.2.1, whisper.cpp active |
| Moonshine v2 (2026) | Small, low latency. Good English for its size | MIT for **English** models. Other languages: Moonshine Community Licence (**non-commercial**) | CPU / edge | Very fast | Word timestamps in its own runtime | Active, small team |
| NVIDIA Canary-180M-flash / Canary-Qwen-2.5B | Canary-Qwen leads the leaderboard (≈5.63 % WER). 180M-flash covers en/es/de/fr | CC-BY-4.0 | 180M on CPU. 2.5B needs a GPU | 2.5B is slow on CPU | Yes (180M) | NeMo |
| SenseVoice-Small (Alibaba) | zh/en/ja/ko/yue, plus emotion and audio events | FunASR Model Licence v1.1: commercial allowed with attribution, but a custom licence. **Flag** | CPU | Very fast (non-autoregressive) | Token | Popular in Asia |
| Qwen3-ASR, Cohere Transcribe 03-2026 (both in sherpa-onnx 1.13.x) | New multilingual LLM-style ASR | Not verified in this pass. **Check before use** | CPU (int8) / GPU | Slower than TDT | Varies | Very new |

### Diarisation
| Option | Quality | Licence | Notes |
|---|---|---|---|
| **sherpa-onnx offline diarisation** = pyannote segmentation-3.0 (ONNX) + 3D-Speaker CAM++/ERes2Net embedding + clustering | Close to pyannote 3.x (same segmentation model). Weaker on heavy overlap | Segmentation MIT. 3D-Speaker models Apache-2.0. sherpa-onnx Apache-2.0 | **Ungated copies on GitHub releases**. 5.7 MB (int8 1.5 MB) + 30-40 MB embedding model. Known or threshold-based speaker count. Per-segment confidence since 1.13.8 |
| pyannote.audio 4.0.7 + `speaker-diarization-community-1` | Best open pipeline (community-1 improves on 3.1) | Code MIT. Pipeline **CC-BY-4.0, gated** on HF (contact details required) | PyTorch. Gating complicates automatic download. The pyannoteAI "precision" models are commercial/proprietary |
| Reverb diarization v1 (Rev) | pyannote 3.0 fine-tuned on Rev data | **Rev Model Non-Production Licence (non-commercial)**. Excluded, even though sherpa-onnx mirrors it | n/a |
| 3D-Speaker toolkit (Alibaba) | CAM++ / ERes2Net with its own clustering pipeline. Multimodal option | Apache-2.0 | ModelScope hosting |
| NeMo TitaNet embeddings | Good English speaker embeddings | CC-BY-4.0 | ONNX in sherpa-onnx releases |

### Audio event classification (AudioSet, 527 classes)
| Option | AudioSet mAP | Licence | Size | Notes |
|---|---|---|---|---|
| **CED-mini / CED-base** (Xiaomi) | 49.0 / 50.0 | Weights Apache-2.0 (HF `mispeech/ced-*`). **Code repo is GPL-3.0**, which we do not ship | 9.6 M / 86 M | ONNX in sherpa-onnx `audio-tagging-models` release. Runs in sherpa-onnx |
| YAMNet | ≈30.6 | Apache-2.0 | 3.7 M | MediaPipe `.tflite` on GCS (521 classes). The `mediapipe` 1.0.1 wheel needs system `libEGL.so.1` |
| EfficientAT mn10 (MIT) | 47.1 | MIT | 4.9 M | Weights on GitHub releases (PyTorch → ONNX export) |
| PANNs CNN14 | 43.1 | MIT | 80 M | Weights on Zenodo (unreachable here) |
| AST | 45.9 | BSD-3-Clause | 87 M | Heavy for CPU |
| BEATs (Microsoft) | ≈48-50 | MIT (unilm repo) | 90 M | Weights on Microsoft blob storage. PyTorch |

### Loudness
`ffmpeg -af ebur128=peak=true` (EBU R128 / ITU-R BS.1770: integrated I, LRA, true peak, plus a
momentary/short-term frame log with `metadata=1`) and `loudnorm=print_format=json` (machine-readable
`input_i`, `input_tp`, `input_lra`, `input_thresh`). Add `astats` (RMS, peak, DC offset, clipping
counts) and `silencedetect`. Alternative: `pyloudnorm` (MIT). This is a deterministic, licence-free
ffmpeg filter chain.

## Evidence
Tested in the sandbox (functional checks only; timings are inflated by a load average of about 20 on
4 vCPUs):
- **sherpa-onnx 1.13.8** from PyPI plus `sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8` from GitHub
  releases. It transcribed the bundled `en.wav` ("Ask not what your country can do for you...") and
  `de.wav` correctly, with per-token timestamps (` A`@0.00, `sk`@0.24, ` not`@0.40...).
  RTF was 1.3-1.5 under that contention. The literature reports roughly 12-18x real time for int8 on
  idle CPUs.
- **CED-mini int8** through `sherpa_onnx.AudioTagging` tagged the bundled clips correctly (Cat/Meow
  0.81, Dog/Bark 0.64, Water/Trickle) in 0.12-0.22 s per clip.
- **ffmpeg 6.1 `ebur128`/`loudnorm`** returned I = -25.3 LUFS, LRA 1.0 LU, TP -6.8 dBFS and JSON
  output as expected.
- The `sherpa-onnx-pyannote-segmentation-3-0` tarball contains `LICENSE` = MIT (CNRS). The
  `moonshine-base-en-quantized-2026-02-27` tarball LICENSE confirms MIT for English only, and the
  Community Licence for other languages.
- Every sherpa-onnx URL in the builder section returned HTTP 200 (HEAD) from the sandbox.

Sources: Open ASR leaderboard summaries
(https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks,
https://www.codesota.com/speech/stt-leaderboard); sherpa-onnx docs and changelog
(https://github.com/k2-fsa/sherpa-onnx/blob/master/CHANGELOG.md: Whisper timestamps #2945,
Moonshine v2 #3232, Qwen3-ASR #3399, Cohere Transcribe #3456, diarisation confidence #3881);
Whisper token-timestamp option in `offline-whisper-model-config.h`; pyannote community-1
(https://huggingface.co/pyannote/speaker-diarization-community-1, CC-BY-4.0, gated); Reverb licence
(https://www.rev.com/blog/introducing-reverb-open-source-asr-diarization); 3D-Speaker Apache-2.0
(https://github.com/modelscope/3D-Speaker); CED (https://github.com/RicherMans/CED,
https://huggingface.co/mispeech/ced-mini); SenseVoice licence discussion
(https://github.com/modelscope/FunASR/issues/3715); Moonshine (https://github.com/moonshine-ai/moonshine);
EfficientAT (https://github.com/fschmid56/EfficientAT, MIT); AST (https://github.com/YuanGongND/ast,
BSD-3); PANNs (https://github.com/qiuqiangkong/audioset_tagging_cnn, MIT); unilm/BEATs
(https://github.com/microsoft/unilm, MIT).

## Decision
- **Runtime: sherpa-onnx (Apache-2.0)** for ASR, VAD, diarisation and tagging. It is one dependency
  with pip wheels for Linux, macOS and Windows, and CPU and CUDA builds. All models come from GitHub
  releases (ungated) and the API is the same in every language binding.
- **ASR default: Parakeet-TDT-0.6B-v3 int8** (CC-BY-4.0, attribution in NOTICE and in the UI's model
  credits) for the 25 European languages. Run it on Silero-VAD (MIT) chunks of 30 s or less, and map
  token timestamps to words.
- **ASR fallback for other languages: Whisper** (MIT) through sherpa-onnx. Pick `turbo` on GPU and
  `small` or `distil-large-v3.5` on CPU (distil is English-only), using the language from Whisper
  language ID. For word timing, prefer an ONNX export with attention outputs
  (`enable_token_timestamps`). Otherwise align segment text to audio with a CTC forced aligner later.
  Apply Whisper hallucination guards: VAD gating, a no-speech threshold, and dropping repeats.
- **Diarisation: sherpa-onnx pyannote-segmentation-3.0 + 3D-Speaker CAM++ (en, voxceleb)** with
  threshold clustering. Speaker embeddings are stored per turn, so a "same speaker across files"
  search can come later. pyannote community-1 is an opt-in "quality" plug-in for users who accept
  its HF gating.
- **Audio events: CED-mini** (default) or CED-base (quality preset) through sherpa-onnx, on 1 s
  hops / 10 s windows. Keep the top-k labels above 0.3 per shot, plus the 527-d class-probability vector
  (ADR 005). YAMNet via MediaPipe is not the default: it is lower quality and needs `libEGL`.
- **Loudness: ffmpeg `ebur128` + `astats` + `silencedetect`** per file. Per-shot values are taken
  from the frame log. No ML is involved.
- Excluded on licence: Reverb diarisation, Moonshine non-English, MiniCPM-o audio, and LFM audio
  models. SenseVoice and Cohere/Qwen3-ASR wait until their licences are reviewed.

## Consequences
- One ONNX-based runtime and no PyTorch at inference time. All default weights (≈700 MB total) are
  fetchable from GitHub releases in CI.
- CC-BY-4.0 attribution must be shown for Parakeet (and TitaNet, if used).
- Two ASR paths (TDT and Whisper) mean two timestamp formats. Normalise both to
  `{word, start, end, conf, speaker}`.
- CPU ASR is the slowest stage after the VLM. Batch it, and process audio in parallel with video
  decoding.

## Revisit when
- A permissively licensed multilingual model beats Whisper for non-European languages with native
  word timestamps (watch Qwen3-ASR and Canary successors once their licences are checked).
- sherpa-onnx ships pyannote community-1-class segmentation or a Sortformer-class end-to-end
  diariser under a permissive licence.
- Users need speaker identification (enrolment). That brings privacy and biometric-law
  review (GDPR Art. 9, BIPA) before any feature work.

## Recommendation for the builder
All confirmed reachable (HTTP 200) from the sandbox. `pip install sherpa-onnx==1.13.8`.
- ASR: `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2` (487 MB)
- Whisper fallback: `.../asr-models/sherpa-onnx-whisper-small.tar.bz2` (639 MB), `.../sherpa-onnx-whisper-turbo.tar.bz2` (564 MB), `.../sherpa-onnx-whisper-distil-large-v3.5.tar.bz2` (529 MB), `.../sherpa-onnx-whisper-tiny.en.tar.bz2` (118 MB, for CI)
- English-only light option: `.../asr-models/sherpa-onnx-moonshine-base-en-quantized-2026-02-27.tar.bz2` (111 MB, MIT)
- VAD: `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx`
- Diarisation: `https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2` + `https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx` (note the upstream typo "recongition")
- Tagging: `https://github.com/k2-fsa/sherpa-onnx/releases/download/audio-tagging-models/sherpa-onnx-ced-mini-audio-tagging-2024-04-19.tar.bz2` (48 MB). Base: `...ced-base-audio-tagging-2024-04-19.tar.bz2` (387 MB)
- Do **not** fetch `sherpa-onnx-reverb-diarization-v1` (non-commercial) even though it is mirrored there.
- Loudness: `ffmpeg -hide_banner -nostats -i in -af ebur128=peak=true:metadata=1,astats=metadata=1 -f null -`

## Outcome (as built, 2026-10-04)

As recommended, via sherpa-onnx: Silero VAD → Parakeet TDT 0.6B v3 int8 (word timings from token timestamps, confidence
from token log-probs) → Whisper-base spoken language identification on the longest segments → pyannote segmentation 3.0
+ TitaNet-small diarisation (CAM++ is the planned swap). The analyser runs only when the audio tagger heard speech, which
skips silent files instantly. CED-mini (Apache-2.0) tags 2 s windows; AudioSet labels map to the `audio_class` vocabulary and
notable events become moments; the 527-d posterior is the audio similarity vector. Loudness is EBU R128 via ffmpeg.

Measured (eval/README.md): WER 15% overall against subtitle references (1.3% on clean speech), 5/5 languages correct.
VAD tuned to threshold 0.25 / min silence 0.8 s (WER 19% → 15% on this small set). Known weakness: speaker counts from
diarisation are approximate (under-clusters very short utterances, over-clusters film dialogue).
