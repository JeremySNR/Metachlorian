"""Dense captions and semantic labels from a vision-language model (local, or a hosted provider the admin enabled).

Sends a 2x2 contact sheet of the shot's keyframes (time order) plus the
deterministic measurements already known (duration, measured camera motion,
people count, transcript and on-screen text) to an OpenAI-compatible endpoint
and asks for a JSON record constrained to the controlled vocabularies. The
model labels and describes; it is told the measured facts and never asked to
invent them. Output failing validation is retried once, then flagged.
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

from ..llm import LimitReached, LLMError, ValidationFailed, codex_remaining, image_part, make_client
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


def batch_schema(n: int) -> dict[str, Any]:
    one = schema()
    return {"type": "object", "additionalProperties": False, "required": ["shots"],
            "properties": {"shots": {"type": "array", "minItems": n, "maxItems": n, "items": one}}}


class CaptionAnalyser(Analyser):
    name = "caption"
    version = "1.1.0"
    requires = ("keyframes", "motion", "people", "ocr", "speech")
    priority = 20
    resource = "model"
    description = "Dense caption, subjects, activities, setting, time of day, weather, mood, location guess (vision-language model)."

    def config(self, settings) -> dict[str, Any]:
        ep = settings.vlm
        return {"provider": ep.provider, "base_url": ep.url, "model": ep.model, "batch": ep.effective_batch,
                "vocab": registry().summary(), "prompt": 1}

    def check(self, settings) -> str | None:
        ep = settings.vlm
        if not ep.enabled:
            return "no vision-language model configured (Settings → Model adapters). CPU-tier zero-shot labels are used instead."
        if not settings.endpoint_allowed(ep):
            return "the configured VLM is hosted and hosted providers are off: content would leave this machine"
        if ep.provider == "codex":
            left = codex_remaining(settings, ep)
            if left is not None and left <= 0:
                return "Codex daily request limit reached; resumes after midnight UTC"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        import cv2

        ep = ctx.settings.vlm
        client = make_client(ep, ctx.settings)
        shots = [s for s in ctx.shots() if s.keyframes]
        size = ep.effective_batch
        batches = [shots[i:i + size] for i in range(0, len(shots), size)]
        if ep.provider == "codex":
            left = codex_remaining(ctx.settings, ep)
            # Each batch may need one corrective retry; don't start a file the budget cannot finish.
            if left is not None and left < math.ceil(len(batches) * 1.2):
                raise Unavailable(f"Codex daily request limit: {left} requests left, this file needs about {len(batches)}")
        t0 = time.time()
        sheets_dir = ctx.work_dir / "vlm"
        sheets_dir.mkdir(parents=True, exist_ok=True)

        def sheet_part(shot) -> dict[str, Any]:
            path = sheets_dir / f"{shot.idx:05d}.jpg"
            cv2.imwrite(str(path), cv2.cvtColor(contact_sheet(ctx, shot.keyframes), cv2.COLOR_RGB2BGR))
            return image_part(path)

        def describe(batch) -> list[tuple[Any, dict[str, Any] | None, dict[str, Any], str | None]]:
            if len(batch) == 1:
                shot = batch[0]
                n = min(4, len(shot.keyframes))
                msgs = [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": [
                            sheet_part(shot),
                            {"type": "text", "text": (f"These are {n} frames from one continuous video shot, in time order"
                                                      f"{' (left to right, top to bottom)' if n > 1 else ''}. {facts_for(ctx, shot)}\n"
                                                      "Log this shot as JSON.")}]}]
                try:
                    obj, usage = client.structured(msgs, schema(), retries=1)
                    return [(shot, obj, usage, None)]
                except ValidationFailed as e:
                    return [(shot, None, {}, f"{e}|{e.raw[:500]}")]
            content: list[dict[str, Any]] = []
            for k, shot in enumerate(batch, 1):
                content.append({"type": "text", "text": f"Shot {k}: frames in time order (left to right, top to bottom). {facts_for(ctx, shot)}"})
                content.append(sheet_part(shot))
            content.append({"type": "text", "text": f"Log each of the {len(batch)} shots as JSON, in order, one record per shot."})
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
            try:
                obj, usage = client.structured(msgs, batch_schema(len(batch)), retries=1)
                return [(shot, rec, usage, None) for shot, rec in zip(batch, obj["shots"])]
            except ValidationFailed as e:
                return [(shot, None, {}, f"{e}|{e.raw[:500]}") for shot in batch]

        done = flagged = tokens = 0
        try:
            with ThreadPoolExecutor(max_workers=ep.effective_concurrency) as pool:
                for results in pool.map(describe, batches):
                    for shot, obj, usage, err in results:
                        if obj is None:
                            msg, _, raw = (err or "").partition("|")
                            ctx.shot_signal(shot, "vlm.error", {"error": msg[:300], "raw": raw}, 0.0)
                            flagged += 1
                            continue
                        tokens += int(usage.get("total_tokens", 0) or 0)
                        conf = 0.7 if usage.get("attempts", 1) == 1 else 0.55
                        ctx.shot_signal(shot, "vlm.record", obj, conf)
                        done += 1
        except LimitReached as e:
            raise Unavailable(str(e)) from e
        except LLMError as e:
            raise Unavailable(f"VLM provider error: {e}") from e
        finally:
            for f in sheets_dir.glob("*.jpg"):
                f.unlink()
        return {"captioned": done, "flagged": flagged, "tokens": tokens, "seconds": round(time.time() - t0, 1),
                "provider": ep.provider, "model": ep.model, "requests": len(batches)}
