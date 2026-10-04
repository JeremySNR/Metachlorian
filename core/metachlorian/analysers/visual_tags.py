"""Zero-shot labels from SigLIP image-text similarity.

This is the CPU-tier labeller: it gives every shot vocabulary labels with a
calibrated confidence even when no vision-language model is configured. When a
VLM runs, fusion prefers the VLM for semantic fields and keeps these as
supporting evidence.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .. import models
from ..db import loads
from ..media import siglip
from ..vocab import registry
from .base import AnalysisContext, Analyser

# Prompt templates per vocabulary; {l} is the term label (lower-cased).
TEMPLATES: dict[str, list[str]] = {
    "setting": ["a photo of {l}", "a video still of {l}"],
    "time_of_day": ["a photo taken at {l}", "a scene at {l}"],
    "weather": ["a photo of {l} weather", "a scene with {l} weather"],
    "season": ["a photo taken in {l}"],
    "shot_size": ["a {l} shot", "a film still, {l}"],
    "camera_angle": ["a photo taken from {l}", "a {l} shot"],
}
# Better wording than the vocabulary label for some terms.
OVERRIDES: dict[tuple[str, str], list[str]] = {
    ("setting", "interior"): ["a photo of an indoor room", "inside a building"],
    ("setting", "exterior"): ["a photo of an outdoor scene", "outdoors"],
    ("setting", "coast"): ["a photo of a coastline with the sea", "a beach by the ocean"],
    ("setting", "open_water"): ["a photo of the open sea", "a boat on open water"],
    ("setting", "screen_capture"): ["a screenshot of a computer screen", "a screen recording of software"],
    ("setting", "animation_graphics"): ["a cartoon animation", "computer generated motion graphics"],
    ("setting", "green_screen"): ["a person in front of a green screen"],
    ("setting", "vehicle_interior"): ["inside a car", "the interior of a vehicle"],
    ("time_of_day", "night"): ["a photo taken at night", "a dark night scene with artificial lights"],
    ("time_of_day", "golden_hour"): ["a photo taken at golden hour with warm low sunlight"],
    ("time_of_day", "day"): ["a photo taken in daylight"],
    ("shot_size", "extreme_close_up"): ["an extreme close-up of a detail", "a macro shot"],
    ("shot_size", "close_up"): ["a close-up of a face", "a close-up shot of an object"],
    ("shot_size", "medium_shot"): ["a medium shot of a person from the waist up"],
    ("shot_size", "long_shot"): ["a full body shot of a person in their surroundings", "a wide shot"],
    ("shot_size", "extreme_wide_shot"): ["an extreme wide shot of a vast landscape", "an establishing shot of a city from far away"],
    ("camera_angle", "aerial_view"): ["an aerial drone shot from high above", "a bird's eye view from a drone"],
    ("camera_angle", "birds_eye"): ["a top-down overhead shot"],
    ("camera_angle", "eye_level"): ["a photo taken at eye level"],
}
# Concepts outside the vocabularies that are useful for search and fusion.
CONCEPTS: dict[str, list[str]] = {
    "people": ["a photo of people", "a person"],
    "crowd": ["a large crowd of people"],
    "no_people": ["an empty scene with no people"],
    "food": ["a photo of food", "a dish of food on a plate"],
    "cooking": ["someone cooking food"],
    "street_food": ["street food stall", "people eating street food"],
    "drone_footage": ["aerial drone footage"],
    "talking_head": ["a person talking to the camera", "an interview with a person speaking"],
    "text_graphics": ["a title card with large text", "on-screen text graphics"],
    "vehicle": ["a car on a road", "a vehicle"],
    "animals": ["an animal", "wildlife"],
    "water": ["water, sea or river"],
    "landmark": ["a famous landmark or monument"],
    "nature": ["nature landscape with trees and hills"],
    "city": ["a city with buildings"],
    "sport": ["people playing sport"],
}
SINGLE = {"time_of_day", "shot_size", "season"}
# Abstract terms an image-text model cannot judge from pixels; left to the VLM and people.
SKIP_TERMS = {("setting", "synthetic"), ("weather", "windy"), ("time_of_day", "morning"), ("time_of_day", "afternoon"),
              ("time_of_day", "midday"), ("season", "wet_season"), ("season", "dry_season")}


def prompt_sets() -> dict[str, dict[str, list[str]]]:
    reg = registry()
    out: dict[str, dict[str, list[str]]] = {}
    for vocab, tmpl in TEMPLATES.items():
        v = reg.get(vocab)
        out[vocab] = {}
        for t in v.terms.values():
            if (vocab, t.id) in SKIP_TERMS:
                continue
            prompts = OVERRIDES.get((vocab, t.id)) or [x.format(l=t.label.lower().split(" / ")[0]) for x in tmpl]
            out[vocab][t.id] = prompts
    out["concept"] = CONCEPTS
    return out


class VisualTagAnalyser(Analyser):
    name = "visual_tags"
    version = "1.1.0"
    requires = ("embed",)
    priority = 75
    resource = "model"
    description = "Zero-shot vocabulary labels (setting, time of day, weather, shot size, angle, concepts) from SigLIP similarity."

    def config(self, settings) -> dict[str, Any]:
        return {"vocab": registry().summary(), "prompts": len(CONCEPTS)}

    def check(self, settings) -> str | None:
        if not models.installed(settings.resolved_models_dir, "siglip-base-multilingual"):
            return "model 'siglip-base-multilingual' is not installed"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        enc = siglip.load(str(ctx.models_dir))
        sets = prompt_sets()
        flat: list[tuple[str, str]] = []
        texts: list[str] = []
        for vocab, terms in sets.items():
            for tid, prompts in terms.items():
                for pr in prompts:
                    flat.append((vocab, tid))
                    texts.append(pr)
        T = enc.encode_texts(texts)
        rows = ctx.db.q("SELECT shot_id, vec FROM vectors WHERE asset_id=? AND space='visual_kf' ORDER BY id", (ctx.asset["id"],))
        by_shot: dict[int, list[np.ndarray]] = {}
        for r in rows:
            by_shot.setdefault(r["shot_id"], []).append(np.frombuffer(r["vec"], dtype=np.float16).astype(np.float32))
        labelled = 0
        for shot_id, vecs in by_shot.items():
            V = np.stack(vecs)
            P = enc.prob(V, T)            # (kf, prompts) sigmoid probabilities
            S = V @ T.T                   # cosine
            agg_p: dict[tuple[str, str], float] = {}
            agg_s: dict[tuple[str, str], float] = {}
            for j, key in enumerate(flat):
                # max over prompts, mean over keyframes
                agg_p[key] = max(agg_p.get(key, 0.0), float(P[:, j].mean()))
                agg_s[key] = max(agg_s.get(key, -1.0), float(S[:, j].mean()))
            result: dict[str, Any] = {}
            for vocab in sets:
                keys = [k for k in agg_s if k[0] == vocab]
                sims = np.array([agg_s[k] for k in keys])
                soft = np.exp((sims - sims.max()) * enc.scale)
                soft /= soft.sum()
                ranked = sorted(zip(keys, soft, [agg_p[k] for k in keys]), key=lambda x: -x[1])
                if vocab in SINGLE:
                    (k, conf, p) = ranked[0]
                    result[vocab] = [{"term": k[1], "confidence": round(float(conf), 3), "p": round(p, 4)}]
                else:
                    keep = [{"term": k[1], "confidence": round(float(c), 3), "p": round(p, 4)} for k, c, p in ranked[:4]
                            if c >= 0.15 or p >= 0.05]
                    result[vocab] = keep
            for vocab, items in result.items():
                if items:
                    name = "zs.concepts" if vocab == "concept" else f"zs.{vocab}"
                    ctx.shot_signal(shot_id, name, items, max(i["confidence"] for i in items))
            labelled += 1
        _ = loads
        return {"shots": labelled, "prompts": len(texts)}
