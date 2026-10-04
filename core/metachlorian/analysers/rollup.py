"""Asset rollup: structure, pacing and edit classification computed from shot
data, plus an asset-level summary (local LLM when configured, otherwise a
deterministic template)."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from ..db import loads
from ..llm import ChatClient, LLMError, ValidationFailed
from ..vocab import registry
from .base import AnalysisContext, Analyser
from .fusion import PACE_ORDER


def classify_edit(f: dict[str, Any]) -> tuple[str, float, dict[str, float]]:
    """raw | selects | finished from structural evidence. Returns (label, confidence, scores)."""
    s_raw = s_sel = s_fin = 0.0
    hard = f["hard_boundaries"]
    cpm = f["cuts_per_minute"]
    # Raw: one continuous take (or a few segments of one), camera metadata, no music bed, no graphics.
    if hard == 0:
        s_raw += 2.0
    elif hard <= 2 and f["duration"] > 60:
        s_raw += 0.8
    if f["camera_metadata"]:
        s_raw += 0.6
    if f["timecode"]:
        s_raw += 0.3
    if f["log_likeness"] > 0.5:
        s_raw += 0.8
    # Selects: several hard cuts, no transitions/titles/music bed, longish shots.
    if hard >= 2:
        s_sel += 1.0
        if f["gradual_transitions"] == 0:
            s_sel += 0.6
        if not f["titles"]:
            s_sel += 0.4
        if not f["music_bed"]:
            s_sel += 0.5
        if f["avg_shot_length"] > 4:
            s_sel += 0.4
    # Finished: transitions, titles, music bed, normalised loudness, fast cutting, fade in/out.
    if f["gradual_transitions"] > 0:
        s_fin += 0.6 + min(0.6, 0.15 * f["gradual_transitions"])
    if f["titles"]:
        s_fin += 0.8
    if f["music_bed"]:
        s_fin += 0.9
    if f["loudness_normalised"]:
        s_fin += 0.5
    if cpm >= 8:
        s_fin += 0.6
    if f["starts_or_ends_black"]:
        s_fin += 0.4
    if f["lower_thirds"] or f["captions"]:
        s_fin += 0.4
    scores = {"raw": s_raw, "selects": s_sel, "finished": s_fin}
    exp = {k: math.exp(v) for k, v in scores.items()}
    tot = sum(exp.values())
    label = max(scores, key=scores.get)
    return label, round(exp[label] / tot, 3), {k: round(v, 2) for k, v in scores.items()}


class RollupAnalyser(Analyser):
    name = "rollup"
    version = "1.0.0"
    requires = ("fusion", "technical", "audio", "speech", "quality")
    priority = 8
    description = "Asset structure (shot count, ASL, cuts/min, single take), pacing and raw/selects/finished classification; asset summary."

    def config(self, settings) -> dict[str, Any]:
        return {"llm": settings.llm.model if settings.endpoint_allowed(settings.llm) else None, "rules": 1}

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        shots = ctx.shots()
        tech = ctx.tech
        dur = float(tech.get("duration") or (shots[-1].end_s if shots else 0))
        trans = Counter(s.transition_in for s in shots[1:])
        hard = sum(v for k, v in trans.items() if k != "continuous")
        gradual = trans.get("dissolve", 0) + trans.get("fade", 0)
        lengths = [s.duration for s in shots] or [dur]
        cpm = hard / (dur / 60) if dur > 0 else 0.0
        sig = {n: ctx.signals_of(n) for n in ("graphics.title", "graphics.lower_third", "graphics.burned_in_captions", "pacing.pace",
                                              "pacing.motion_energy", "content.setting", "content.time_of_day", "semantic.topics", "shot.role",
                                              "content.caption", "content.location_guess", "people.count", "camera.movement")}
        audio_share = (ctx.output_of("audio").get("class_share") or {})
        loud = ctx.output_of("audio").get("integrated_lufs")
        music = audio_share.get("music", 0.0)
        speech = audio_share.get("speech", 0.0)
        blank = set(ctx.output_of("shots").get("blank_shots", []))
        features = {
            "duration": dur, "shot_count": len(shots), "hard_boundaries": hard, "gradual_transitions": gradual,
            "cuts_per_minute": round(cpm, 2), "avg_shot_length": round(float(np.mean(lengths)), 2),
            "median_shot_length": round(float(np.median(lengths)), 2),
            "titles": any(sig["graphics.title"].get(s.id) for s in shots),
            "lower_thirds": any(sig["graphics.lower_third"].get(s.id) for s in shots),
            "captions": any(sig["graphics.burned_in_captions"].get(s.id) for s in shots),
            "music_bed": music >= 0.5, "music_share": round(music, 3), "speech_share": round(speech, 3),
            "loudness_normalised": loud is not None and any(abs(loud - t) <= 1.5 for t in (-14, -16, -23, -24)),
            "integrated_lufs": loud,
            "camera_metadata": bool(tech.get("camera_make") or tech.get("camera_model")),
            "timecode": bool(tech.get("timecode")),
            "log_likeness": float(ctx.output_of("quality").get("log_likeness") or 0.0),
            "starts_or_ends_black": bool(shots) and (0 in blank or (len(shots) - 1) in blank),
            "single_take": hard == 0,
            "transitions": dict(trans),
        }
        label, conf, scores = classify_edit(features)
        paces = [(sig["pacing.pace"].get(s.id) or {}).get("term") for s in shots]
        pace_idx = [PACE_ORDER.index(p) for p in paces if p in PACE_ORDER]
        # Asset pace also reflects cutting rate.
        cut_factor = min(4.0, cpm / 10)
        asset_pace = PACE_ORDER[int(round(min(4, (np.mean(pace_idx) if pace_idx else 1) * 0.7 + cut_factor * 0.6)))]
        settings_c: Counter = Counter()
        tod_c: Counter = Counter()
        topics_c: Counter = Counter()
        roles_c: Counter = Counter()
        moves_c: Counter = Counter()
        for s in shots:
            for x in sig["content.setting"].get(s.id) or []:
                settings_c[x["term"]] += s.duration
            if (t := sig["content.time_of_day"].get(s.id)):
                tod_c[t["term"]] += s.duration
            for x in sig["semantic.topics"].get(s.id) or []:
                topics_c[x["term"]] += 1
            for x in sig["shot.role"].get(s.id) or []:
                roles_c[x["term"]] += 1
            for x in sig["camera.movement"].get(s.id) or []:
                moves_c[x["term"]] += 1
        locs = Counter((sig["content.location_guess"].get(s.id) or {}).get("value") for s in shots)
        locs.pop(None, None)
        locs.pop("", None)
        structure = {**features, "edit_type": {"term": label, "confidence": conf, "scores": scores},
                     "pace": asset_pace, "top_settings": [k for k, _ in settings_c.most_common(4)],
                     "time_of_day": [k for k, _ in tod_c.most_common(2)], "topics": [k for k, _ in topics_c.most_common(6)],
                     "roles": dict(roles_c), "camera_movements": dict(moves_c.most_common(8)),
                     "locations": [k for k, _ in locs.most_common(3)],
                     "people_shots": sum(1 for s in shots if ((sig["people.count"].get(s.id) or {}).get("value") or 0) > 0)}
        summary = self._summary(ctx, structure, shots, sig)
        structure["summary"] = summary
        ctx.asset_updates["summary"] = structure
        ctx.asset_signal("structure.edit_type", structure["edit_type"], conf)
        ctx.asset_signal("structure.shot_count", len(shots), 1.0)
        ctx.asset_signal("structure.cuts_per_minute", features["cuts_per_minute"], 1.0)
        ctx.asset_signal("structure.avg_shot_length", features["avg_shot_length"], 1.0)
        ctx.asset_signal("structure.single_take", features["single_take"], 1.0)
        ctx.asset_signal("pacing.pace", {"term": asset_pace, "confidence": 0.6}, 0.6)
        ctx.asset_signal("semantic.summary", summary, summary.get("confidence", 0.4))
        return {"edit_type": label, "confidence": conf, "shots": len(shots), "cpm": features["cuts_per_minute"]}

    def _summary(self, ctx: AnalysisContext, st: dict[str, Any], shots, sig) -> dict[str, Any]:
        reg = registry()
        mins, secs = divmod(int(round(st["duration"])), 60)
        kind = {"raw": "Raw footage", "selects": "Selects reel", "finished": "Finished edit"}[st["edit_type"]["term"]]
        bits = [f"{kind}, {mins} min {secs} s" if mins else f"{kind}, {secs} s",
                "one continuous take" if st["single_take"] else f"{st['shot_count']} shots ({st['cuts_per_minute']} cuts/min)"]
        extras = [x for x, on in (("music bed", st["music_bed"]), ("titles", st["titles"]), ("lower thirds", st["lower_thirds"]),
                                  ("speech", st["speech_share"] > 0.2)) if on]
        if extras:
            bits.append(", ".join(extras))
        if st["top_settings"]:
            bits.append("mostly " + " / ".join(reg.label("setting", t).lower() for t in st["top_settings"][:2]))
        if st["time_of_day"]:
            bits.append(reg.label("time_of_day", st["time_of_day"][0]).lower())
        text = "; ".join(bits) + "."
        out = {"text": text, "source": "template", "confidence": 0.5}
        if not ctx.settings.endpoint_allowed(ctx.settings.llm):
            return out
        caps = [(sig["content.caption"].get(s.id) or {}).get("value") for s in shots[:40]]
        transcript = ctx.db.q1("SELECT value FROM signals WHERE asset_id=? AND name='audio.transcript' AND level='asset'", (ctx.asset["id"],))
        schema = {"type": "object", "additionalProperties": False, "required": ["story", "topics"],
                  "properties": {"story": {"type": "string", "minLength": 20, "maxLength": 600},
                                 "topics": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 6}}}
        msgs = [{"role": "system", "content": "You summarise video files for a footage library. Be factual and brief. British English."},
                {"role": "user", "content": (f"Structure: {text}\nShot captions in order: {caps}\n"
                                             f"Transcript excerpt: {(loads(transcript['value']) if transcript else '')[:1500]}\n"
                                             "Write a 2-3 sentence story summary of what this file shows and its main topics as JSON.")}]
        try:
            obj, _ = ChatClient(ctx.settings.llm, ctx.settings).structured(msgs, schema, retries=1, max_tokens=500)
            return {"text": text, "story": obj["story"], "topics": obj["topics"], "source": "llm", "confidence": 0.6}
        except (LLMError, ValidationFailed) as e:
            return {**out, "llm_error": str(e)[:200]}
