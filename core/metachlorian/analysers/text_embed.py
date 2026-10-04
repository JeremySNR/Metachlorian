"""Semantic text vectors per shot from what was said and what the shot is
described as (transcript + caption + on-screen text), using the multilingual
SigLIP text tower. Lets "an interview line about family holidays" match
speech that never uses those words."""
from __future__ import annotations

from typing import Any

from .. import models
from ..media import siglip
from .base import AnalysisContext, Analyser


class TextEmbedAnalyser(Analyser):
    name = "text_embed"
    version = "1.0.0"
    requires = ("fusion", "speech", "ocr")
    priority = 9
    description = "Multilingual text embeddings of each shot's transcript, caption and on-screen text for semantic matching."

    def config(self, settings) -> dict[str, Any]:
        return {"model": "siglip-base-multilingual", "fields": ["audio.transcript", "content.caption", "content.ocr_text"]}

    def check(self, settings) -> str | None:
        if not models.installed(settings.resolved_models_dir, "siglip-base-multilingual"):
            return "model 'siglip-base-multilingual' is not installed"
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        enc = siglip.load(str(ctx.models_dir))
        transcripts = ctx.signals_of("audio.transcript")
        captions = ctx.signals_of("content.caption")
        ocr = ctx.signals_of("content.ocr_text")
        n = 0
        texts, ids = [], []
        for s in ctx.shots():
            cap = captions.get(s.id)
            cap = cap.get("value") if isinstance(cap, dict) else cap
            # Template captions (CPU tier) are label lists already covered by term search; skip them.
            if isinstance(captions.get(s.id), dict) and "fusion_rules" in (captions[s.id].get("sources") or []):
                cap = None
            parts = [p for p in (transcripts.get(s.id), cap, ocr.get(s.id)) if p]
            if not parts:
                continue
            texts.append(" . ".join(str(p) for p in parts)[:600])
            ids.append(s.id)
        if texts:
            V = enc.encode_texts(texts)
            for sid, v in zip(ids, V):
                ctx.vector(sid, "text", v)
                n += 1
        return {"shots": n}
