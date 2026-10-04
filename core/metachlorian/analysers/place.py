from __future__ import annotations

from typing import Any

from ..geo import reverse
from .base import AnalysisContext, Analyser


class PlaceAnalyser(Analyser):
    name = "place"
    version = "1.0.0"
    requires = ("technical",)
    priority = 98
    description = "GPS to the nearest town or city, region and country (offline GeoNames lookup). Deterministic."

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        gps = ctx.tech.get("gps")
        if not gps:
            return {"gps": False}
        place = reverse(gps.get("lat"), gps.get("lon"))
        if not place:
            return {"gps": True, "place": None}
        # Close to a known place: confident; far from any (at sea, wilderness): say so.
        conf = 0.95 if place["distance_km"] < 15 else 0.6 if place["distance_km"] < 60 else 0.3
        ctx.asset_signal("content.place", place, conf)
        return {"gps": True, "place": place}
