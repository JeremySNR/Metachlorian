"""On-screen text via RapidOCR (PP-OCR models, Apache-2.0) on keyframes.

Also derives graphics signals used by the asset rollup: titles (large centred
text), lower thirds (text in the lower band), burned-in captions (changing
text in the bottom band across keyframes)."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import cv2
import numpy as np

from .base import AnalysisContext, Analyser, Moment
from .embed import load_keyframe


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR(use_cls=False)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


class OcrAnalyser(Analyser):
    name = "ocr"
    version = "1.1.0"
    requires = ("keyframes",)
    priority = 45
    description = "On-screen text with positions, titles, lower thirds and burned-in captions."

    def check(self, settings) -> str | None:
        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError:
            return "RapidOCR is not installed: pip install rapidocr-onnxruntime"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        eng = _engine()
        n_text = 0
        for shot in ctx.shots():
            if not shot.keyframes:
                continue
            items: list[dict[str, Any]] = []
            bottom_texts = []
            kfs = shot.keyframes
            if len(kfs) > 3:  # first, middle, last: enough for titles, lower thirds and captions
                kfs = [kfs[0], kfs[len(kfs) // 2], kfs[-1]]
            # Middle keyframe first; the others only when it shows text (needed to tell titles, lower thirds
            # and changing captions apart). Most shots have no text, so this saves two detector passes each.
            if len(kfs) > 1:
                mid = len(kfs) // 2
                kfs = [kfs[mid]] + kfs[:mid] + kfs[mid + 1:]
            last_small, last_res = None, None
            for n, kf in enumerate(kfs):
                if n == 1 and not items:
                    break
                rgb = load_keyframe(ctx, kf)
                H, W = rgb.shape[:2]
                small = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
                if last_small is not None and float(np.abs(small - last_small).mean()) < 0.015:
                    res = last_res  # near-identical frame (static shot): same text
                else:
                    res, _ = eng(rgb, use_cls=False)
                    last_small, last_res = small, res
                for box, text, score in res or []:
                    text = _norm(text)
                    if score < 0.6 or len(text) < 2:
                        continue
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    b = [min(xs) / W, min(ys) / H, max(xs) / W, max(ys) / H]
                    h = b[3] - b[1]
                    region = "lower_third" if b[1] > 0.62 else "top" if b[3] < 0.25 else "centre"
                    items.append({"t": kf["t"], "text": text, "conf": round(float(score), 3), "box": [round(v, 4) for v in b],
                                  "height": round(h, 4), "region": region})
                    if b[1] > 0.75:
                        bottom_texts.append((kf["t"], text))
            if not items:
                continue
            # De-duplicate text repeated across keyframes.
            seen: dict[str, dict[str, Any]] = {}
            for it in items:
                key = it["text"].lower()
                if key not in seen or it["conf"] > seen[key]["conf"]:
                    seen[key] = {**it, "first": min(it["t"], seen.get(key, it)["t"])}
            uniq = sorted(seen.values(), key=lambda x: x["first"])
            text = " · ".join(u["text"] for u in uniq)
            area = sum((u["box"][2] - u["box"][0]) * (u["box"][3] - u["box"][1]) for u in uniq)
            big_centre = [u for u in uniq if u["region"] == "centre" and u["height"] > 0.06]
            lower = [u for u in uniq if u["region"] == "lower_third"]
            captions = len({t for _, t in bottom_texts}) >= 2 and len(kfs) >= 2
            ctx.shot_signal(shot, "content.ocr_text", text, max(u["conf"] for u in uniq))
            ctx.shot_signal(shot, "graphics.text_area", round(min(1.0, area), 4), 1.0)
            ctx.shot_signal(shot, "graphics.title", bool(big_centre), 0.6 if big_centre else 0.5)
            ctx.shot_signal(shot, "graphics.lower_third", bool(lower) and not captions, 0.55)
            ctx.shot_signal(shot, "graphics.burned_in_captions", captions, 0.55)
            for u in uniq:
                ctx.moment(Moment(shot.id, "text", max(shot.start_s, u["first"] - 0.5), min(shot.end_s, u["first"] + 1.5), u["text"],
                                  {"box": u["box"], "region": u["region"]}, u["conf"]))
            n_text += 1
        return {"shots_with_text": n_text}
