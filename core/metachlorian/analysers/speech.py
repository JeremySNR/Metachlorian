"""Speech: VAD (Silero), transcription with word timings (NVIDIA Parakeet TDT
0.6B v3, 25 European languages), spoken language identification (Whisper
base) and speaker diarisation (pyannote segmentation 3.0 + TitaNet), all via
sherpa-onnx on CPU. Runs only when the audio analyser heard speech."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .. import models
from ..media import ffmpeg
from .base import AnalysisContext, Analyser, Moment, Unavailable

LANGS = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "pt": "Portuguese", "nl": "Dutch",
         "pl": "Polish", "sv": "Swedish", "da": "Danish", "fi": "Finnish", "el": "Greek", "cs": "Czech", "ro": "Romanian",
         "hu": "Hungarian", "bg": "Bulgarian", "hr": "Croatian", "sk": "Slovak", "sl": "Slovenian", "et": "Estonian",
         "lv": "Latvian", "lt": "Lithuanian", "mt": "Maltese", "uk": "Ukrainian", "ru": "Russian"}


def _recognizer(d):
    import sherpa_onnx as so

    return so.OfflineRecognizer.from_transducer(encoder=str(d / "encoder.int8.onnx"), decoder=str(d / "decoder.int8.onnx"),
                                                joiner=str(d / "joiner.int8.onnx"), tokens=str(d / "tokens.txt"),
                                                num_threads=max(1, min(4, (__import__("os").cpu_count() or 2))), model_type="nemo_transducer")


def _vad(d):
    import sherpa_onnx as so

    cfg = so.VadModelConfig()
    cfg.silero_vad.model = str(d / "silero_vad.onnx")
    # Tuned on eval/asr (WER 19% -> 15%): a permissive threshold keeps quiet dialogue and longer
    # segments give the recogniser more context.
    cfg.silero_vad.min_silence_duration = 0.8
    cfg.silero_vad.min_speech_duration = 0.2
    cfg.silero_vad.max_speech_duration = 25
    cfg.silero_vad.threshold = 0.25
    cfg.sample_rate = 16000
    return so.VoiceActivityDetector(cfg, buffer_size_in_seconds=600)


def words_from(result, offset: float) -> list[dict[str, Any]]:
    toks, ts = list(result.tokens), list(result.timestamps)
    durs = list(getattr(result, "durations", []) or [])
    lps = list(getattr(result, "ys_log_probs", []) or [])
    words: list[dict[str, Any]] = []
    for i, tok in enumerate(toks):
        start = offset + ts[i]
        end = start + (durs[i] if i < len(durs) and durs[i] > 0 else 0.08)
        p = math.exp(lps[i]) if i < len(lps) else None
        if (tok.startswith(" ") or tok.startswith("▁") or not words) and tok.strip(" ▁") and tok.strip(" ▁")[0].isalnum():
            words.append({"w": tok.strip(" ▁"), "s": round(start, 3), "e": round(end, 3), "p": [p] if p is not None else []})
        elif words:
            words[-1]["w"] += tok.strip("▁") if not tok.startswith(" ") else tok.strip()
            words[-1]["e"] = round(end, 3)
            if p is not None:
                words[-1]["p"].append(p)
    for w in words:
        w["p"] = round(float(np.mean(w["p"])), 3) if w["p"] else None
    return words


class SpeechAnalyser(Analyser):
    name = "speech"
    version = "1.1.0"
    requires = ("audio",)
    priority = 40
    resource = "model"
    description = "Transcript with word timings, language and speaker turns. Local models only."

    def config(self, settings) -> dict[str, Any]:
        root = settings.resolved_models_dir
        return {"asr": "parakeet-tdt-0.6b-v3", "lid": models.installed(root, "whisper-base"),
                "diar": models.installed(root, "pyannote-segmentation-3.0") and models.installed(root, "titanet-small")}

    def check(self, settings) -> str | None:
        root = settings.resolved_models_dir
        for m in ("parakeet-tdt-0.6b-v3", "silero-vad"):
            if not models.installed(root, m):
                return f"model '{m}' is not installed. Run: metachlorian models fetch {m}"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        audio_out = ctx.output_of("audio")
        share = (audio_out.get("class_share") or {})
        if not ctx.audio_path.exists() or not audio_out.get("has_audio"):
            return {"skipped": "no audio"}
        if audio_out.get("tagger") and share.get("speech", 0) + share.get("crowd_speech", 0) + share.get("singing", 0) < 0.02:
            return {"skipped": "no speech detected"}
        root = ctx.models_dir
        wav, sr = ffmpeg.read_wav_mono(ctx.audio_path)
        rec = models.cached(("parakeet", str(root)), lambda: _recognizer(models.model_dir(root, "parakeet-tdt-0.6b-v3")))
        vad = _vad(models.model_dir(root, "silero-vad"))
        segments: list[tuple[float, np.ndarray]] = []
        win = 512
        for i in range(0, len(wav), win):
            vad.accept_waveform(wav[i:i + win])
            while not vad.empty():
                seg = vad.front
                segments.append((seg.start / sr, np.array(seg.samples, dtype=np.float32)))
                vad.pop()
        vad.flush()
        while not vad.empty():
            seg = vad.front
            segments.append((seg.start / sr, np.array(seg.samples, dtype=np.float32)))
            vad.pop()
        if not segments:
            return {"skipped": "VAD found no speech"}
        utterances = []
        for start, samples in segments:
            st = rec.create_stream()
            # Small padding helps the first word.
            pad = np.zeros(int(0.15 * sr), np.float32)
            st.accept_waveform(sr, np.concatenate([pad, samples, pad]))
            rec.decode_stream(st)
            r = st.result
            text = r.text.strip()
            if not text:
                continue
            words = words_from(r, start - 0.15)
            conf = float(np.mean([w["p"] for w in words if w["p"] is not None])) if words else None
            utterances.append({"start": round(start, 3), "end": round(start + len(samples) / sr, 3), "text": text, "words": words,
                               "confidence": round(conf, 3) if conf is not None else None})
        language = self._language(root, wav, sr, segments)
        speakers = self._diarise(root, wav, sr) if len(utterances) >= 1 else []
        for u in utterances:
            u["speaker"] = _speaker_at(speakers, (u["start"] + u["end"]) / 2)
        shots = ctx.shots()
        for u in utterances:
            sid = next((s.id for s in shots if s.start_s <= (u["start"] + u["end"]) / 2 < s.end_s), shots[-1].id if shots else None)
            ctx.moment(Moment(sid, "speech", u["start"], u["end"], u["text"],
                              {"words": u["words"], "speaker": u["speaker"], "language": language.get("code")}, u["confidence"]))
        for s in shots:
            words = [w for u in utterances for w in u["words"] if s.start_s <= (w["s"] + w["e"]) / 2 < s.end_s]
            if not words:
                continue
            text = " ".join(w["w"] for w in words)
            spk = sorted({u["speaker"] for u in utterances if u["end"] > s.start_s and u["start"] < s.end_s and u["speaker"] is not None})
            speech_s = sum(min(w["e"], s.end_s) - max(w["s"], s.start_s) for w in words)
            ctx.shot_signal(s, "audio.transcript", text, float(np.mean([w["p"] for w in words if w["p"] is not None] or [0.5])))
            ctx.shot_signal(s, "audio.speakers", spk, 0.7 if spk else 0.0)
            ctx.shot_signal(s, "audio.speech_ratio", round(min(1.0, speech_s / max(0.1, s.duration)), 3), 1.0)
            ctx.shot_signal(s, "audio.words_per_minute", round(len(words) / max(0.1, s.duration) * 60, 1), 1.0)
        if language:
            ctx.asset_signal("audio.language", language, language.get("confidence", 0.5))
        ctx.asset_signal("audio.speaker_count", len({sp for _, _, sp in speakers}), 0.7 if speakers else 0.0)
        full = " ".join(u["text"] for u in utterances)
        ctx.asset_signal("audio.transcript", full, 1.0)
        return {"utterances": len(utterances), "words": sum(len(u["words"]) for u in utterances), "language": language,
                "speakers": len({sp for _, _, sp in speakers})}

    def _language(self, root, wav, sr, segments) -> dict[str, Any]:
        if not models.installed(root, "whisper-base"):
            return {}
        import sherpa_onnx as so

        d = models.model_dir(root, "whisper-base")

        def make():
            cfg = so.SpokenLanguageIdentificationConfig(
                whisper=so.SpokenLanguageIdentificationWhisperConfig(encoder=str(d / "base-encoder.int8.onnx"), decoder=str(d / "base-decoder.int8.onnx")),
                num_threads=2)
            return so.SpokenLanguageIdentification(cfg)

        lid = models.cached(("lid", str(d)), make)
        # Up to 30 s of speech from the longest segments.
        segs = sorted(segments, key=lambda s: -len(s[1]))
        votes: dict[str, float] = {}
        for _, samples in segs[:3]:
            st = lid.create_stream()
            st.accept_waveform(sr, samples[: 30 * sr])
            code = lid.compute(st)
            votes[code] = votes.get(code, 0) + len(samples)
        if not votes:
            return {}
        code = max(votes, key=votes.get)
        return {"code": code, "name": LANGS.get(code, code), "confidence": round(votes[code] / sum(votes.values()), 3)}

    def _diarise(self, root, wav, sr) -> list[tuple[float, float, int]]:
        if not (models.installed(root, "pyannote-segmentation-3.0") and models.installed(root, "titanet-small")):
            return []
        import sherpa_onnx as so

        seg_dir = models.model_dir(root, "pyannote-segmentation-3.0")
        emb_dir = models.model_dir(root, "titanet-small")
        cfg = so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg_dir / "model.onnx"))),
            embedding=so.SpeakerEmbeddingExtractorConfig(model=str(emb_dir / "nemo_en_titanet_small.onnx")),
            clustering=so.FastClusteringConfig(num_clusters=-1, threshold=0.6),
            min_duration_on=0.3, min_duration_off=0.5)
        if not cfg.validate():
            raise Unavailable("speaker diarisation config invalid")
        sd = so.OfflineSpeakerDiarization(cfg)
        if sd.sample_rate != sr:
            return []
        result = sd.process(wav).sort_by_start_time()
        return [(r.start, r.end, int(r.speaker)) for r in result]


def _speaker_at(speakers: list[tuple[float, float, int]], t: float) -> int | None:
    best = None
    for s, e, k in speakers:
        if s <= t <= e:
            return k
        d = min(abs(t - s), abs(t - e))
        if best is None or d < best[0]:
            best = (d, k)
    return best[1] if best and best[0] < 1.0 else None
