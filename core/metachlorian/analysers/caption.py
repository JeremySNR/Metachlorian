"""Dense captions and semantic labels from a local vision-language model.

Sends a 2x2 contact sheet of the shot's keyframes (time order) plus the
deterministic measurements already known (duration, measured camera motion,
people count, transcript and on-screen text) to an OpenAI-compatible endpoint
and asks for a JSON record constrained to the controlled vocabularies. The
model labels and describes; it is told the measured facts and never asked to
invent them. Output failing validation is retried once, then flagged.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from ..llm import ChatClient, LLMError, ValidationFailed, image_part
from ..vocab import registry
from .base import AnalysisContext, Analyser, Unavailable
from .embed import load_keyframe

ANGLES = ["eye_level", "high_angle", "low_angle", "birds_eye", "aerial_view", "dutch_angle", "pov", "over_the_shoulder"]


def schema() -> dict[str, Any]:
    reg = registry()

    def terms(v: str) -> list[str]:
        return list(reg.get(v).terms)

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["caption", "subjects", "activities", "setting", "time_of_day", "weather", "shot_size", "camera_angle",
                     "aerial", "people_visible", "mood", "location_guess", "visible_text_or_logos", "topics"],
        "properties": {
            "caption": {"type": "string", "minLength": 10, "maxLength": 400},
            "subjects": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 6},
            "activities": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 4},
            "setting": {"type": "array", "items": {"enum": terms("setting")}, "maxItems": 3},
            "time_of_day": {"enum": terms("time_of_day") + ["unknown"]},
            "weather": {"type": "array", "items": {"enum": terms("weather")}, "maxItems": 2},
            "shot_size": {"enum": terms("shot_size")},
            "camera_angle": {"enum": ANGLES},
            "aerial": {"type": "boolean"},
            "people_visible": {"type": "integer", "minimum": 0, "maximum": 200},
            "mood": {"type": "array", "items": {"enum": terms("mood")}, "maxItems": 2},
            "location_guess": {"type": "string", "maxLength": 80},
            "visible_text_or_logos": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 5},
            "topics": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 4},
        },
    }


SYSTEM = ("You are a meticulous footage logger for a professional video library. You describe exactly what is visible, "
          "in plain British English, without guessing names of people. Use only the allowed values for labelled fields. "
          "If something cannot be seen, use an empty list, 'unknown' or an empty string.")


def contact_sheet(ctx: AnalysisContext, kfs: list[dict[str, Any]], tile_w: int = 384) -> np.ndarray:
    import cv2

    imgs = [load_keyframe(ctx, k) for k in kfs[:4]]
    h = int(round(tile_w * imgs[0].shape[0] / imgs[0].shape[1]))
    tiles = [cv2.resize(im, (tile_w, h), interpolation=cv2.INTER_AREA) for im in imgs]
    if len(tiles) == 1:
        return tiles[0]
    while len(tiles) < 4:
        tiles.append(np.zeros_like(tiles[0]))
    if len(imgs) == 2:
        return np.hstack(tiles[:2])
    return np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])])


def facts_for(ctx: AnalysisContext, shot) -> str:
    def first(name: str, default=None):
        return ctx.signals_of(name).get(shot.id, default)

    mv = first("camera.movement", []) or []
    lines = [f"Duration: {shot.duration:.1f} s."]
    if mv:
        lines.append("Measured camera movement (optical flow): " + ", ".join(m["term"] for m in mv) + ".")
    pc = first("people.count")
    if pc is not None:
        lines.append(f"Person detector count: {pc}.")
    tr = first("audio.transcript")
    if tr:
        lines.append(f"Speech in this shot: \"{tr[:300]}\"")
    ocr = first("content.ocr_text")
    if ocr:
        lines.append(f"On-screen text read by OCR: \"{ocr[:200]}\"")
    return " ".join(lines)


class CaptionAnalyser(Analyser):
    name = "caption"
    version = "1.0.0"
    requires = ("keyframes", "motion", "people", "ocr", "speech")
    priority = 20
    resource = "model"
    description = "Dense caption, subjects, activities, setting, time of day, weather, mood, location guess (local VLM)."

    def config(self, settings) -> dict[str, Any]:
        return {"base_url": settings.vlm.base_url, "model": settings.vlm.model, "vocab": registry().summary(), "prompt": 1}

    def check(self, settings) -> str | None:
        if not settings.vlm.enabled:
            return "no vision-language model configured (settings: vlm.base_url, vlm.model). CPU-tier zero-shot labels are used instead."
        if not settings.endpoint_allowed(settings.vlm):
            return "the configured VLM is remote and allow_remote is off: content would leave this machine"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        import cv2

        client = ChatClient(ctx.settings.vlm, ctx.settings)
        sch = schema()
        done = flagged = 0
        tokens = 0
        t0 = time.time()
        sheet_path = ctx.work_dir / "vlm_sheet.jpg"
        for shot in ctx.shots():
            if not shot.keyframes:
                continue
            sheet = contact_sheet(ctx, shot.keyframes)
            cv2.imwrite(str(sheet_path), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
            n = min(4, len(shot.keyframes))
            msgs = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    image_part(sheet_path),
                    {"type": "text", "text": (f"These are {n} frames from one continuous video shot, in time order"
                                              f"{' (left to right, top to bottom)' if n > 1 else ''}. {facts_for(ctx, shot)}\n"
                                              "Log this shot as JSON.")},
                ]},
            ]
            try:
                obj, usage = client.structured(msgs, sch, retries=1)
            except ValidationFailed as e:
                ctx.shot_signal(shot, "vlm.error", {"error": str(e)[:300], "raw": e.raw[:500]}, 0.0)
                flagged += 1
                continue
            except LLMError as e:
                raise Unavailable(f"VLM endpoint error: {e}") from e
            tokens += int(usage.get("total_tokens", 0) or 0)
            conf = 0.7 if usage.get("attempts", 1) == 1 else 0.55
            ctx.shot_signal(shot, "vlm.record", obj, conf)
            done += 1
        if sheet_path.exists():
            sheet_path.unlink()
        return {"captioned": done, "flagged": flagged, "tokens": tokens, "seconds": round(time.time() - t0, 1),
                "model": ctx.settings.vlm.model}
