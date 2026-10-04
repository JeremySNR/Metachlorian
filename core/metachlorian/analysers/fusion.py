"""Fusion: combine analyser outputs into one validated shot record.

Two layers:

1. Rules (always): resolve each field from its evidence with explicit
   precedence and confidence. Measured fields (duration, motion, counts,
   loudness, quality) come only from measurements.
2. Language model (when ``llm`` is configured): given the rule record and the
   evidence, it writes the summary and may refine role, pace, mood, topics and
   suggested uses. Its output must validate against a JSON schema built from
   the vocabularies; invalid output is retried once, then the rule record is
   kept and the shot flagged. The model cannot touch measured fields.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..llm import ChatClient, LLMError, ValidationFailed
from ..vocab import registry
from .base import AnalysisContext, Analyser, ShotRow

W_VLM, W_MEASURED, W_ZS = 0.75, 1.0, 0.55
PACE_ORDER = ["still", "slow", "moderate", "fast", "frenetic"]


def _get(sig: dict[str, dict[int, Any]], name: str, sid: int, default=None):
    return sig.get(name, {}).get(sid, default)


def pick_single(cands: list[tuple[str | None, float, str]]) -> dict[str, Any] | None:
    """Pick the best of (term, confidence, source) candidates, summing agreeing evidence."""
    score: dict[str, float] = {}
    srcs: dict[str, list[str]] = {}
    for term, conf, src in cands:
        if not term or term == "unknown":
            continue
        score[term] = score.get(term, 0.0) + conf
        srcs.setdefault(term, []).append(src)
    if not score:
        return None
    best = max(score, key=score.get)
    total = sum(score.values())
    agree = len(srcs[best])
    conf = min(0.97, score[best] / max(total, 1e-9) * (0.55 + 0.15 * agree))
    return {"term": best, "confidence": round(conf, 3), "sources": srcs[best]}


def merge_multi(lists: list[tuple[list[dict[str, Any]], float, str]], keep: float = 0.3, limit: int = 6) -> list[dict[str, Any]]:
    acc: dict[str, dict[str, Any]] = {}
    for items, weight, src in lists:
        for it in items or []:
            t = it["term"] if isinstance(it, dict) else it
            c = (it.get("confidence", 0.7) if isinstance(it, dict) else 0.7) * weight
            cur = acc.setdefault(t, {"term": t, "confidence": 0.0, "sources": []})
            cur["confidence"] = 1 - (1 - cur["confidence"]) * (1 - c)  # noisy-or
            cur["sources"].append(src)
    out = sorted((v for v in acc.values() if v["confidence"] >= keep), key=lambda v: -v["confidence"])
    for v in out:
        v["confidence"] = round(v["confidence"], 3)
    return out[:limit]


def pace_label(duration: float, motion: float | None, change: float | None, audio: float | None) -> tuple[str, float]:
    m = motion or 0.0
    c = min(1.0, (change or 0.0) * 6)
    a = audio if audio is not None else 0.3
    length = float(np.clip(1.0 - (duration - 1.0) / 12.0, 0, 1))  # short shots read faster
    score = 0.35 * m + 0.25 * c + 0.15 * a + 0.25 * length
    if score < 0.12:
        lbl = "still"
    elif score < 0.3:
        lbl = "slow"
    elif score < 0.5:
        lbl = "moderate"
    elif score < 0.7:
        lbl = "fast"
    else:
        lbl = "frenetic"
    edges = [0.12, 0.3, 0.5, 0.7]
    margin = min(abs(score - e) for e in edges)
    return lbl, round(float(min(0.95, 0.55 + margin * 3)), 3)


class FusionAnalyser(Analyser):
    name = "fusion"
    version = "1.1.0"
    requires = ("shots", "keyframes", "motion", "quality", "audio", "speech", "people", "ocr", "visual_tags", "caption", "embed")
    priority = 10
    description = "Rule-based evidence fusion into the shot record, refined by a local language model when configured."

    def config(self, settings) -> dict[str, Any]:
        return {"llm": settings.llm.model if settings.endpoint_allowed(settings.llm) else None, "vocab": registry().summary(), "rules": 1}

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        shots = ctx.shots()
        names = ["camera.movement", "camera.shot_size_measured", "people.count", "people.faces", "people.centred_face", "people.face_presence",
                 "audio.speech_ratio", "audio.classes", "audio.transcript", "pacing.motion_energy", "pacing.audio_energy", "quality.sharpness",
                 "quality.flags_measured", "quality.stability", "quality.exposure", "graphics.title", "graphics.text_area", "content.ocr_text",
                 "content.objects_detected", "composition.saliency_centre", "people.boxes", "vlm.record", "zs.setting", "zs.time_of_day",
                 "zs.weather", "zs.season", "zs.shot_size", "zs.camera_angle", "zs.concepts", "pacing.visual_variety"]
        sig = {n: ctx.signals_of(n) for n in names}
        seg = ctx.output_of("shots")
        change = seg.get("visual_change", [])
        blank = set(seg.get("blank_shots", []))
        tech = ctx.tech
        records: dict[int, dict[str, Any]] = {}
        for i, s in enumerate(shots):
            records[s.id] = self._rules(s, i, sig, change, blank, tech)
        self._context_roles(shots, records)
        llm_info = {"used": False}
        if ctx.settings.endpoint_allowed(ctx.settings.llm):
            llm_info = self._llm_refine(ctx, shots, records, sig)
        for s in shots:
            rec = records[s.id]
            for field, val in rec.items():
                if field.startswith("_"):
                    continue
                conf = val.get("confidence") if isinstance(val, dict) else (max((v.get("confidence", 0) for v in val), default=0)
                                                                            if isinstance(val, list) and val and isinstance(val[0], dict) else 1.0)
                ctx.shot_signal(s, field, val, conf)
        return {"shots": len(shots), "llm": llm_info}

    # ------------------------------------------------------------------ rules
    def _rules(self, s: ShotRow, i: int, sig, change, blank, tech) -> dict[str, Any]:
        sid = s.id
        vlm = _get(sig, "vlm.record", sid) or {}
        zs = {k: _get(sig, f"zs.{k}", sid) or [] for k in ("setting", "time_of_day", "weather", "season", "shot_size", "camera_angle", "concepts")}
        concepts = {c["term"]: c for c in zs["concepts"]}
        rec: dict[str, Any] = {}
        # Camera movement: measured, plus aerial evidence from VLM / zero-shot.
        moves = [dict(m, sources=["motion"]) for m in (_get(sig, "camera.movement", sid) or [])]
        aerial_ev = []
        if vlm.get("aerial"):
            aerial_ev.append(0.7)
        if vlm.get("camera_angle") == "aerial_view":
            aerial_ev.append(0.6)
        for z in zs["camera_angle"]:
            if z["term"] == "aerial_view" and z["confidence"] > 0.35:
                aerial_ev.append(z["confidence"] * 0.8)
        if "drone_footage" in concepts and concepts["drone_footage"]["p"] > 0.02:
            aerial_ev.append(min(0.8, 0.4 + concepts["drone_footage"]["p"] * 5))
        if "aerial" in concepts and (concepts["aerial"]["p"] > 0.03 or concepts["aerial"]["confidence"] > 0.3):
            aerial_ev.append(min(0.8, 0.45 + concepts["aerial"]["p"] * 4))
        if aerial_ev:
            c = 1 - float(np.prod([1 - a for a in aerial_ev]))
            if c >= 0.45:
                moves.append({"term": "aerial", "confidence": round(c, 3), "sources": ["vlm" if vlm.get("aerial") else "visual_tags"]})
        rec["camera.movement"] = moves
        # Shot size.
        cands = []
        m_size = _get(sig, "camera.shot_size_measured", sid)
        if m_size:
            cands.append((m_size, 0.6 * W_MEASURED, "people"))
        if vlm.get("shot_size"):
            cands.append((vlm["shot_size"], W_VLM, "vlm"))
        if zs["shot_size"]:
            cands.append((zs["shot_size"][0]["term"], zs["shot_size"][0]["confidence"] * W_ZS, "visual_tags"))
        if (p := pick_single(cands)):
            rec["camera.shot_size"] = p
        # Angle.
        cands = []
        if vlm.get("camera_angle"):
            cands.append((vlm["camera_angle"], W_VLM, "vlm"))
        if zs["camera_angle"]:
            cands.append((zs["camera_angle"][0]["term"], zs["camera_angle"][0]["confidence"] * W_ZS, "visual_tags"))
        if (p := pick_single(cands)):
            rec["camera.angle"] = p
        # Content.
        rec["content.setting"] = merge_multi([([{"term": t, "confidence": 0.8} for t in vlm.get("setting", [])], W_VLM, "vlm"),
                                              (zs["setting"], W_ZS, "visual_tags")])
        for field, single in (("time_of_day", True), ("weather", False), ("season", True)):
            if single:
                cands = []
                if vlm.get(field) and vlm.get(field) != "unknown":
                    cands.append((vlm[field], W_VLM, "vlm"))
                if zs[field]:
                    cands.append((zs[field][0]["term"], zs[field][0]["confidence"] * W_ZS * (0.6 if field == "season" else 1), "visual_tags"))
                if (p := pick_single(cands)):
                    rec[f"content.{field}"] = p
            else:
                rec[f"content.{field}"] = merge_multi([([{"term": t, "confidence": 0.75} for t in vlm.get(field, [])], W_VLM, "vlm"),
                                                       (zs[field], W_ZS * 0.8, "visual_tags")], keep=0.3, limit=2)
        objects = [{"term": o["label"], "confidence": o["confidence"]} for o in (_get(sig, "content.objects_detected", sid) or [])]
        rec["content.objects"] = merge_multi([(objects, W_MEASURED, "people"),
                                              ([{"term": x.lower(), "confidence": 0.7} for x in vlm.get("subjects", [])], W_VLM, "vlm")], keep=0.3, limit=10)
        if vlm.get("activities"):
            rec["content.activities"] = [{"term": a.lower(), "confidence": 0.6, "sources": ["vlm"]} for a in vlm["activities"]]
        if vlm.get("caption"):
            rec["content.caption"] = {"value": vlm["caption"], "confidence": 0.7, "sources": ["vlm"]}
        if vlm.get("location_guess"):
            rec["content.location_guess"] = {"value": vlm["location_guess"], "confidence": 0.35, "sources": ["vlm"]}
        if vlm.get("visible_text_or_logos"):
            rec["content.logos_text"] = {"value": vlm["visible_text_or_logos"], "confidence": 0.5, "sources": ["vlm"]}
        concept_terms = [c for c in zs["concepts"] if c["confidence"] >= 0.2 or c.get("p", 0) > 0.05]
        if concept_terms:
            rec["content.concepts"] = [{"term": c["term"], "confidence": c["confidence"], "sources": ["visual_tags"]} for c in concept_terms]
        # People.
        pc = _get(sig, "people.count", sid)
        vpc = vlm.get("people_visible")
        if pc is not None or vpc is not None:
            if pc is not None and (vpc is None or pc > 0 or vpc == 0):
                rec["people.count"] = {"value": int(pc), "confidence": 0.75, "sources": ["people"]}
            else:
                rec["people.count"] = {"value": int(vpc), "confidence": 0.55, "sources": ["vlm"]}
        # Detectors miss small people in crowds: a confident crowd concept lifts the count to "many".
        crowd = concepts.get("crowd")
        if rec.get("people.count") and crowd and (crowd["confidence"] >= 0.25 or crowd.get("p", 0) > 0.05) and rec["people.count"]["value"] >= 2:
            rec["people.count"] = {"value": max(rec["people.count"]["value"], 6), "confidence": 0.5, "sources": ["people", "visual_tags"],
                                   "detected": rec["people.count"]["value"]}
        speech_ratio = _get(sig, "audio.speech_ratio", sid) or 0.0
        centred = bool(_get(sig, "people.centred_face", sid))
        talking = centred and speech_ratio > 0.35
        rec["people.talking_to_camera"] = {"value": talking, "confidence": 0.6 if talking else 0.5, "sources": ["people", "speech"]}
        # Pacing.
        dur = s.duration
        ch = change[i] if i < len(change) else None
        motion = _get(sig, "pacing.motion_energy", sid)
        audio_e = _get(sig, "pacing.audio_energy", sid)
        lbl, pconf = pace_label(dur, motion, ch, audio_e)
        rec["pacing.pace"] = {"term": lbl, "confidence": pconf, "sources": ["motion", "shots", "audio"]}
        # Semantic.
        if vlm.get("mood"):
            rec["semantic.mood"] = [{"term": m, "confidence": 0.55, "sources": ["vlm"]} for m in vlm["mood"]]
        if vlm.get("topics"):
            rec["semantic.topics"] = [{"term": t.lower(), "confidence": 0.55, "sources": ["vlm"]} for t in vlm["topics"]]
        # Quality and usability.
        flags = list(_get(sig, "quality.flags_measured", sid) or [])
        stab = _get(sig, "quality.stability", sid)
        if stab is not None and stab < 0.2 and "camera_shake" not in flags:
            flags.append("camera_shake")
        is_blank = i in blank
        sharp = _get(sig, "quality.sharpness", sid) or 0.0
        severe = {"out_of_focus", "underexposed", "overexposed"} & set(flags)
        usable = not is_blank and dur >= 1.0 and not severe
        score = float(np.clip(0.45 * min(1.0, sharp / 0.45) + 0.25 * (stab if stab is not None else 0.7) + 0.3 * (0 if severe else 1), 0, 1))
        rec["quality.flags"] = [{"term": f, "confidence": 0.7, "sources": ["quality"]} for f in flags]
        rec["quality.usable"] = {"value": usable, "confidence": 0.7, "sources": ["quality", "motion", "shots"],
                                 "reason": "blank frames" if is_blank else "too short" if dur < 1.0 else ", ".join(sorted(severe)) or "ok"}
        rec["quality.score"] = {"value": round(score, 3), "confidence": 0.8, "sources": ["quality", "motion"]}
        rec["composition.vertical_crop"] = self._vertical_crop(sig, sid, tech)
        rec["_ctx"] = {"speech_ratio": speech_ratio, "centred": centred, "blank": is_blank, "duration": dur,
                       "title": bool(_get(sig, "graphics.title", sid)), "text_area": _get(sig, "graphics.text_area", sid) or 0.0,
                       "faces": _get(sig, "people.faces", sid) or 0, "variety": _get(sig, "pacing.visual_variety", sid) or 0.0}
        return rec

    @staticmethod
    def _vertical_crop(sig, sid, tech) -> dict[str, Any]:
        aspect = tech.get("aspect_ratio") or 16 / 9
        win = (9 / 16) / aspect  # crop width as a fraction of frame width
        if win >= 1:
            return {"value": {"x_centre": 0.5, "width": 1.0, "safe": True}, "confidence": 0.9, "sources": ["technical"]}
        boxes = _get(sig, "people.boxes", sid) or []
        xs = []
        for b in boxes:
            faces = b.get("faces") or []
            if faces:
                f = max(faces, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
                xs.append((f[0] + f[2]) / 2)
            elif b.get("persons"):
                p = max(b["persons"], key=lambda p: (p[2] - p[0]) * (p[3] - p[1]))
                xs.append((p[0] + p[2]) / 2)
        src = "people"
        if not xs:
            sal = _get(sig, "composition.saliency_centre", sid)
            xs = [sal[0]] if sal else [0.5]
            src = "quality"
        cx = float(np.clip(np.median(xs), win / 2, 1 - win / 2))
        spread = float(np.max(xs) - np.min(xs)) if len(xs) > 1 else 0.0
        safe = spread < win * 0.8
        return {"value": {"x_centre": round(cx, 3), "width": round(win, 3), "safe": safe}, "confidence": 0.6 if src == "people" else 0.4,
                "sources": [src]}

    @staticmethod
    def _context_roles(shots: list[ShotRow], records: dict[int, dict[str, Any]]) -> None:
        """Editorial role from shot evidence and neighbours."""
        for i, s in enumerate(shots):
            r = records[s.id]
            c = r["_ctx"]
            size = (r.get("camera.shot_size") or {}).get("term")
            moves = {m["term"] for m in r.get("camera.movement", [])}
            settings = {x["term"] for x in r.get("content.setting", [])}
            roles: list[tuple[str, float]] = []
            if c["blank"]:
                roles.append(("transition", 0.8))
            elif c["title"] and c["text_area"] > 0.04:
                roles.append(("title_card", 0.6))
            elif c["speech_ratio"] > 0.35 and c["faces"] >= 1:
                handheld = "handheld" in moves or "tracking" in moves
                roles.append(("a_roll", 0.65))
                roles.append(("piece_to_camera" if handheld and c["centred"] else "interview", 0.5 if c["centred"] else 0.4))
            else:
                roles.append(("b_roll", 0.6))
                wide = size in ("extreme_wide_shot", "long_shot")
                if wide and ("aerial" in moves or i == 0 or "exterior" in settings or "urban" in settings):
                    roles.append(("establishing", 0.5 if "aerial" in moves or i == 0 else 0.4))
                if wide and not c["faces"]:
                    roles.append(("general_view", 0.45))
                if size in ("extreme_close_up", "close_up") and not c["faces"]:
                    roles.append(("insert", 0.5))
                prev_a = i > 0 and any(t == "a_roll" for t, _ in records[shots[i - 1].id].get("_roles", []))
                nxt = records[shots[i + 1].id]["_ctx"] if i + 1 < len(shots) else None
                if prev_a and nxt and nxt["speech_ratio"] > 0.35 and c["duration"] < 6:
                    roles.append(("cutaway", 0.55))
            r["_roles"] = roles
            r["shot.role"] = [{"term": t, "confidence": round(cf, 3), "sources": ["fusion_rules"]} for t, cf in roles]
            uses = []
            if any(t == "establishing" for t, _ in roles):
                uses.append("opening or scene-setting shot")
            if any(t in ("b_roll", "general_view") for t, _ in roles):
                uses.append("B-roll under voice-over")
            if any(t == "cutaway" for t, _ in roles):
                uses.append("cutaway to cover an edit")
            vc = r.get("composition.vertical_crop", {}).get("value", {})
            if vc.get("safe") and c["duration"] >= 2:
                uses.append("vertical social (9:16 crop)")
            if any(t in ("interview", "a_roll") for t, _ in roles):
                uses.append("soundbite")
            r["semantic.suggested_uses"] = [{"term": u, "confidence": 0.5, "sources": ["fusion_rules"]} for u in uses]
            if "content.caption" not in r:
                r["content.caption"] = {"value": template_caption(r), "confidence": 0.35, "sources": ["fusion_rules"]}
        for r in records.values():
            r.pop("_roles", None)

    # ------------------------------------------------------------------ language model
    def _llm_refine(self, ctx: AnalysisContext, shots, records, sig) -> dict[str, Any]:
        reg = registry()
        client = ChatClient(ctx.settings.llm, ctx.settings)
        item = {
            "type": "object", "additionalProperties": False,
            "required": ["index", "summary", "role", "pace", "mood", "topics", "suggested_uses"],
            "properties": {
                "index": {"type": "integer"},
                "summary": {"type": "string", "minLength": 10, "maxLength": 300},
                "role": {"type": "array", "items": {"enum": list(reg.get("shot_role").terms)}, "minItems": 1, "maxItems": 3},
                "pace": {"enum": list(reg.get("pace").terms)},
                "mood": {"type": "array", "items": {"enum": list(reg.get("mood").terms)}, "maxItems": 2},
                "topics": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 4},
                "suggested_uses": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 3},
            },
        }
        schema = {"type": "object", "additionalProperties": False, "required": ["shots"],
                  "properties": {"shots": {"type": "array", "items": item}}}
        used = flagged = 0
        batch = 6
        for b in range(0, len(shots), batch):
            chunk = shots[b:b + batch]
            evidence = []
            for k, s in enumerate(chunk):
                r = records[s.id]
                evidence.append({
                    "index": k, "duration_s": round(s.duration, 2),
                    "caption": r.get("content.caption", {}).get("value"),
                    "camera_movement": [m["term"] for m in r.get("camera.movement", [])],
                    "shot_size": (r.get("camera.shot_size") or {}).get("term"),
                    "setting": [x["term"] for x in r.get("content.setting", [])],
                    "people": (r.get("people.count") or {}).get("value"),
                    "speech": (_get(sig, "audio.transcript", s.id) or "")[:200],
                    "on_screen_text": (_get(sig, "content.ocr_text", s.id) or "")[:120],
                    "rule_role": [x["term"] for x in r.get("shot.role", [])],
                    "rule_pace": r["pacing.pace"]["term"],
                })
            msgs = [{"role": "system", "content": "You are a senior video editor finishing a footage log. Use only allowed vocabulary values. "
                                                  "Do not contradict measured facts (duration, camera movement, people count)."},
                    {"role": "user", "content": "For each shot below, write a one-sentence summary and choose its editorial role(s), pace, "
                                                "mood, topics and suggested uses. Return JSON {\"shots\": [...]} with one entry per index.\n"
                                                + __import__("json").dumps(evidence, ensure_ascii=False)}]

            def check(obj: dict[str, Any]) -> list[str]:
                idx = sorted(x["index"] for x in obj["shots"])
                return [] if idx == list(range(len(chunk))) else [f"expected indexes 0..{len(chunk) - 1}, got {idx}"]

            try:
                obj, _ = client.structured(msgs, schema, retries=1, extra_check=check, max_tokens=1600)
            except ValidationFailed as e:
                flagged += len(chunk)
                for s in chunk:
                    records[s.id]["fusion.flag"] = {"value": f"LLM output rejected: {str(e)[:200]}", "confidence": 1.0, "sources": ["fusion"]}
                continue
            except LLMError as e:
                return {"used": False, "error": str(e)[:300]}
            for x in obj["shots"]:
                s = chunk[x["index"]]
                r = records[s.id]
                r["content.summary"] = {"value": x["summary"], "confidence": 0.6, "sources": ["llm"]}
                r["shot.role"] = merge_multi([(r["shot.role"], 1.0, "fusion_rules"),
                                              ([{"term": t, "confidence": 0.6} for t in x["role"]], 1.0, "llm")], keep=0.3, limit=4)
                # Pace: the LLM may move the rule label by at most one step.
                ri, li = PACE_ORDER.index(r["pacing.pace"]["term"]), PACE_ORDER.index(x["pace"])
                if abs(ri - li) == 1:
                    r["pacing.pace"] = {"term": x["pace"], "confidence": 0.55, "sources": ["fusion_rules", "llm"]}
                if x["mood"]:
                    r["semantic.mood"] = merge_multi([(r.get("semantic.mood", []), 1.0, "vlm"),
                                                      ([{"term": t, "confidence": 0.55} for t in x["mood"]], 1.0, "llm")], keep=0.3, limit=3)
                if x["topics"]:
                    r["semantic.topics"] = [{"term": t.lower(), "confidence": 0.55, "sources": ["llm"]} for t in x["topics"]]
                if x["suggested_uses"]:
                    r["semantic.suggested_uses"] = [{"term": u, "confidence": 0.55, "sources": ["llm"]} for u in x["suggested_uses"]]
                used += 1
        return {"used": True, "shots": used, "flagged": flagged, "model": ctx.settings.llm.model}


def template_caption(r: dict[str, Any]) -> str:
    """Plain caption assembled from labels when no VLM is available."""
    reg = registry()
    parts = []
    size = (r.get("camera.shot_size") or {}).get("term")
    if size:
        parts.append(reg.label("shot_size", size))
    setting = [x["term"] for x in r.get("content.setting", [])[:2]]
    if setting:
        parts.append(" / ".join(reg.label("setting", t).lower() for t in setting))
    pc = (r.get("people.count") or {}).get("value")
    if pc:
        parts.append(f"{pc} {'person' if pc == 1 else 'people'}")
    objs = [o["term"] for o in r.get("content.objects", [])[:3]]
    if objs:
        parts.append(", ".join(objs))
    tod = (r.get("content.time_of_day") or {}).get("term")
    if tod:
        parts.append(reg.label("time_of_day", tod).lower())
    mv = [m["term"] for m in r.get("camera.movement", []) if m["term"] not in ("static",)]
    if mv:
        parts.append(", ".join(reg.label("camera_movement", m).lower() for m in mv[:2]))
    return (". ".join(p[0].upper() + p[1:] for p in parts if p) + ".") if parts else "Shot."
