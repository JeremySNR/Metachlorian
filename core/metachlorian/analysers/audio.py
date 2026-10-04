"""Audio: EBU R128 loudness (ffmpeg), energy and silence (signal processing),
and AudioSet event tagging (CED-mini, Apache-2.0) mapped to the audio_class
vocabulary. The 527-class posterior per shot doubles as an audio embedding for
"sounds like this" similarity."""
from __future__ import annotations

import csv
import re
from typing import Any

import numpy as np

from .. import models
from ..media import ffmpeg
from .base import AnalysisContext, Analyser, Moment

CLASS_RULES: list[tuple[str, str]] = [
    ("speech", r"^(Speech|Male speech|Female speech|Child speech|Conversation|Narration|Speech synthesizer)"),
    ("crowd_speech", r"^(Chatter|Crowd|Hubbub|Babbling)"),
    ("singing", r"^(Singing|Choir|Chant|Male singing|Female singing|Child singing|Rapping|Humming|Yodeling)"),
    ("music", r"^(Music|Musical instrument|Pop music|Rock music|Electronic music|Hip hop music|Ambient music|Background music|Soundtrack music|Theme music|Jingle|Orchestra|Piano|Guitar|Drum|Classical music|Jazz|Dance music|Song|Video game music|Christmas music|Wedding music|Happy music|Sad music|Tender music|Exciting music|Angry music|Scary music)"),
    ("applause", r"^(Applause|Clapping|Cheering)"),
    ("laughter", r"^(Laughter|Giggle|Chuckle|Belly laugh|Baby laughter|Snicker)"),
    ("traffic_urban", r"^(Vehicle|Car|Traffic noise|Bus|Truck|Motorcycle|Siren|Car passing by|Train|Subway|Tram|Honk|Vehicle horn|Police car|Ambulance|Fire engine|Aircraft|Helicopter|Skateboard)"),
    ("machinery", r"^(Engine|Mechanisms|Tools|Power tool|Drill|Machine|Sewing machine|Mechanical fan|Air conditioning|Printer|Idling)"),
    ("animal_sound", r"^(Animal|Dog|Cat|Bird|Livestock|Horse|Cattle|Pig|Goat|Sheep|Fowl|Chicken|Rooster|Duck|Goose|Insect|Cricket|Frog|Roaring cats|Bark|Meow|Chirp)"),
    ("nature_sound", r"^(Wind|Rain|Raindrop|Thunder|Thunderstorm|Water|Stream|Waterfall|Ocean|Waves|Rustling leaves|Fire|Crackle|Bird vocalization|Bird song)"),
    ("ambience", r"^(Inside, small room|Inside, large room|Outside, urban|Outside, rural|Environmental noise|Static|Hum|Noise|White noise|Pink noise|Reverberation|Echo)"),
]
NOTABLE = re.compile(r"^(Applause|Laughter|Siren|Explosion|Gunshot|Fireworks|Dog|Bark|Thunder|Bell|Church bell|Horn|Vehicle horn|Cheering|Crowd|Glass|Shatter|Doorbell|Telephone|Alarm|Baby cry|Crying|Scream|Whistle|Boat|Train horn|Splash|Waves)")


def _labels(path) -> list[str]:
    with open(path) as f:
        r = csv.DictReader(f)
        return [row["display_name"] for row in r]


class AudioAnalyser(Analyser):
    name = "audio"
    version = "1.0.0"
    requires = ("shots",)
    priority = 55
    description = "Loudness (EBU R128), audio energy, silence, and speech/music/ambience/event classification (CED-mini)."

    def config(self, settings) -> dict[str, Any]:
        return {"tagger": "ced-mini" if models.installed(settings.resolved_models_dir, "ced-mini") else None, "win": 2.0}

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        shots = ctx.shots()
        if not ctx.audio_path.exists():
            for s in shots:
                ctx.shot_signal(s, "audio.classes", [{"term": "silence", "confidence": 1.0}], 1.0)
                ctx.shot_signal(s, "audio.has_audio", False, 1.0)
            ctx.asset_signal("audio.has_audio", False, 1.0)
            return {"has_audio": False}
        loud = ffmpeg.loudness(ctx.source_path)
        ctx.asset_signal("audio.loudness", {k: v for k, v in loud.items() if k != "momentary"}, 1.0)
        mom = np.array(loud["momentary"]) if loud["momentary"] else np.zeros((0, 2))
        wav, sr = ffmpeg.read_wav_mono(ctx.audio_path)
        # Tagging windows.
        tagger = None
        names: list[str] = []
        if models.installed(ctx.models_dir, "ced-mini"):
            import sherpa_onnx as so

            d = models.model_dir(ctx.models_dir, "ced-mini")
            names = _labels(d / "class_labels_indices.csv")
            tagger = models.cached(("ced", str(d)), lambda: so.AudioTagging(so.AudioTaggingConfig(
                model=so.AudioTaggingModelConfig(ced=str(d / "model.int8.onnx"), num_threads=2), labels=str(d / "class_labels_indices.csv"), top_k=len(names))))
        win, hop = 2.0, 1.0
        times, probs = [], []
        if tagger is not None:
            t = 0.0
            dur = len(wav) / sr
            while t < max(dur - 0.25, 0.01):
                seg = wav[int(t * sr): int(min(dur, t + win) * sr)]
                if len(seg) < sr * 0.25:
                    break
                st = tagger.create_stream()
                st.accept_waveform(sr, seg)
                ev = tagger.compute(st, len(names))
                vec = np.zeros(len(names), np.float32)
                for e in ev:
                    vec[e.index] = e.prob
                times.append(t)
                probs.append(vec)
                t += hop
        P = np.stack(probs) if probs else np.zeros((0, len(names)), np.float32)
        T = np.array(times)
        class_idx = {c: [i for i, n in enumerate(names) if re.match(rx, n)] for c, rx in CLASS_RULES}
        summary_classes: dict[str, float] = {}
        for s in shots:
            a, b = int(s.start_s * sr), int(s.end_s * sr)
            seg = wav[a:b]
            rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
            rms_db = 20 * np.log10(rms + 1e-9)
            frames = seg[: len(seg) // 1600 * 1600].reshape(-1, 1600) if len(seg) >= 1600 else seg.reshape(1, -1) if len(seg) else np.zeros((1, 1))
            fr_db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
            silence = float(np.mean(fr_db < -50))
            m = mom[(mom[:, 0] >= s.start_s) & (mom[:, 0] < s.end_s)] if len(mom) else np.zeros((0, 2))
            m_vals = m[:, 1][m[:, 1] > -70] if len(m) else np.array([])
            ctx.shot_signal(s, "audio.loudness_lufs", round(float(np.mean(m_vals)), 2) if len(m_vals) else None, 1.0)
            ctx.shot_signal(s, "audio.peak_momentary_lufs", round(float(np.max(m_vals)), 2) if len(m_vals) else None, 1.0)
            ctx.shot_signal(s, "pacing.audio_energy", round(float(np.clip((rms_db + 50) / 40, 0, 1)), 4), 1.0)
            ctx.shot_signal(s, "audio.silence_ratio", round(silence, 3), 1.0)
            ctx.shot_signal(s, "audio.has_audio", True, 1.0)
            classes: list[dict[str, Any]] = []
            if len(T):
                sel = (T + win > s.start_s) & (T < s.end_s)
                if not sel.any():
                    sel = np.abs(T - s.start_s) == np.abs(T - s.start_s).min()
                sp = P[sel]
                mean = sp.mean(axis=0)
                peak = sp.max(axis=0)
                ctx.vector(s.id, "audio", mean / (np.linalg.norm(mean) + 1e-8))
                for c, idxs in class_idx.items():
                    if not idxs:
                        continue
                    score = float(max(mean[idxs].max(), 0.7 * peak[idxs].max()))
                    if score >= 0.2:
                        classes.append({"term": c, "confidence": round(min(1.0, score * 1.3), 3)})
                        summary_classes[c] = summary_classes.get(c, 0) + s.duration
                top = np.argsort(-peak)[:8]
                events = [{"label": names[i], "p": round(float(peak[i]), 3)} for i in top if peak[i] > 0.25]
                ctx.shot_signal(s, "audio.events", events, max((e["p"] for e in events), default=0.0))
                for e in events:
                    if NOTABLE.match(e["label"]) and e["p"] > 0.4:
                        when = T[sel][int(np.argmax(sp[:, names.index(e['label'])]))]
                        ctx.moment(Moment(s.id, "sound", float(max(s.start_s, when)), float(min(s.end_s, when + win)), e["label"],
                                          {"p": e["p"]}, e["p"]))
            if silence > 0.85:
                classes = [{"term": "silence", "confidence": round(silence, 3)}] + [c for c in classes if c["term"] != "speech"]
            classes.sort(key=lambda c: -c["confidence"])
            ctx.shot_signal(s, "audio.classes", classes, classes[0]["confidence"] if classes else 0.0)
        total = sum(s.duration for s in shots) or 1.0
        ctx.asset_signal("audio.class_share", {k: round(v / total, 3) for k, v in summary_classes.items()}, 1.0)
        ctx.asset_signal("audio.has_audio", True, 1.0)
        return {"has_audio": True, "integrated_lufs": loud.get("integrated_lufs"), "class_share": {k: round(v / total, 3) for k, v in summary_classes.items()},
                "tagger": bool(tagger)}
