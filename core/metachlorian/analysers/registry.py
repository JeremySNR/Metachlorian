"""The analyser DAG. Order here is only a tie-break; dependencies decide."""
from __future__ import annotations

from functools import lru_cache

from .base import Analyser


@lru_cache(maxsize=1)
def all_analysers() -> dict[str, Analyser]:
    from .audio import AudioAnalyser
    from .caption import CaptionAnalyser
    from .embed import EmbedAnalyser
    from .faces import FacesAnalyser
    from .fusion import FusionAnalyser
    from .keyframes import KeyframeAnalyser
    from .motion import MotionAnalyser
    from .ocr import OcrAnalyser
    from .people import PeopleAnalyser
    from .place import PlaceAnalyser
    from .proxy import ProxyAnalyser
    from .quality import QualityAnalyser
    from .rollup import RollupAnalyser
    from .segment import ShotAnalyser
    from .speech import SpeechAnalyser
    from .technical import TechnicalAnalyser
    from .text_embed import TextEmbedAnalyser
    from .visual_tags import VisualTagAnalyser

    items = [TechnicalAnalyser(), PlaceAnalyser(), ProxyAnalyser(), ShotAnalyser(), KeyframeAnalyser(), EmbedAnalyser(), VisualTagAnalyser(),
             MotionAnalyser(), QualityAnalyser(), AudioAnalyser(), SpeechAnalyser(), OcrAnalyser(), PeopleAnalyser(), FacesAnalyser(),
             CaptionAnalyser(), FusionAnalyser(), RollupAnalyser(), TextEmbedAnalyser()]
    return {a.name: a for a in items}


def get(name: str) -> Analyser | None:
    return all_analysers().get(name)


@lru_cache(maxsize=1)
def _topo() -> tuple[Analyser, ...]:
    items = all_analysers()
    order: list[Analyser] = []
    seen: set[str] = set()

    def visit(n: str, stack: tuple[str, ...] = ()) -> None:
        if n in seen:
            return
        if n in stack:
            raise ValueError(f"analyser cycle: {' -> '.join(stack + (n,))}")
        for d in items[n].requires:
            if d not in items:
                raise ValueError(f"{n} requires unknown analyser {d}")
            visit(d, stack + (n,))
        seen.add(n)
        order.append(items[n])

    for n in items:
        visit(n)
    return tuple(order)


def topological() -> tuple[Analyser, ...]:
    return _topo()
