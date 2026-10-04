"""Analyser contract.

Each analyser is an independent, versioned module. Its *input key* is a hash
of the file content, its own name/version/config and the input keys of the
analysers it depends on. A job only runs when that key has no finished run,
so upgrading one analyser re-runs just that analyser and its dependants, and
unchanged files are never re-processed.

Analysers never write to the database directly: they buffer signals and
moments on the context, and the worker commits them atomically together with
the run record, replacing that analyser's previous output for the asset.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..config import Settings
    from ..db import Database


class Unavailable(Exception):
    """The analyser cannot run here (missing model, endpoint or dependency).

    Recorded as status 'unavailable' with the reason; dependants continue.
    """


class CannotDecode(Exception):
    """The file cannot be read here (no decoder for its format). Permanent: not retried, the file is marked
    as an error with this message, and it is tried again when the decoding setup changes."""


@dataclass
class Signal:
    level: str  # asset | shot
    target_id: int
    name: str
    value: Any
    confidence: float | None = None


@dataclass
class Moment:
    shot_id: int | None
    kind: str
    start_s: float
    end_s: float
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None


@dataclass
class ShotRow:
    id: int
    uid: str
    idx: int
    start_s: float
    end_s: float
    start_frame: int
    end_frame: int
    kind: str
    transition_in: str
    keyframes: list[dict[str, Any]]

    @property
    def duration(self) -> float:
        return max(0.0, self.end_s - self.start_s)


class AnalysisContext:
    def __init__(self, db: "Database", settings: "Settings", asset: dict[str, Any], analyser: "Analyser"):
        self.db = db
        self.settings = settings
        self.asset = asset
        self.analyser = analyser
        self.signals: list[Signal] = []
        self.moments: list[Moment] = []
        self.new_shots: list[dict[str, Any]] | None = None  # set only by the segmenter
        self.keyframe_updates: dict[int, list[dict[str, Any]]] = {}
        self.asset_updates: dict[str, Any] = {}
        self.vectors: list[tuple[int, str, Any]] = []  # (shot_id, space, np.ndarray)
        self.faces: list[dict[str, Any]] | None = None  # set only by the faces analyser

    # -------------------------------------------------------------- paths
    @property
    def work_dir(self) -> Path:
        d = self.settings.media_dir / self.asset["uid"]
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def source_path(self) -> Path:
        return Path(self.asset.get("local_path") or self.asset["path"])

    @property
    def proxy_path(self) -> Path:
        return self.work_dir / "proxy.mp4"

    @property
    def audio_path(self) -> Path:
        return self.work_dir / "audio16k.wav"

    @property
    def models_dir(self) -> Path:
        return self.settings.resolved_models_dir

    def analysis_input(self) -> Path:
        """The rendition analysers decode: the proxy when it exists."""
        return self.proxy_path if self.proxy_path.exists() else self.source_path

    # -------------------------------------------------------------- reads
    @property
    def tech(self) -> dict[str, Any]:
        from ..db import loads

        return loads(self.asset.get("tech"), {}) or {}

    def shots(self) -> list[ShotRow]:
        from ..db import loads

        rows = self.db.q("SELECT * FROM shots WHERE asset_id=? AND active=1 ORDER BY idx", (self.asset["id"],))
        return [ShotRow(r["id"], r["uid"], r["idx"], r["start_s"], r["end_s"], r["start_frame"], r["end_frame"], r["kind"],
                        r["transition_in"], loads(r["keyframes"], [])) for r in rows]

    def output_of(self, analyser: str) -> dict[str, Any]:
        from ..db import loads

        r = self.db.q1("SELECT output, status FROM analysis_runs WHERE asset_id=? AND analyser=?", (self.asset["id"], analyser))
        if not r or r["status"] != "done":
            return {}
        return loads(r["output"], {}) or {}

    def signals_of(self, name: str, level: str = "shot", source: str | None = None) -> dict[int, Any]:
        from ..db import loads

        """Values of one signal for this asset, keyed by target. Never returns this
        analyser's own (stale) output; when several analysers write the same
        name, fusion wins over the others."""
        sql = "SELECT target_id, value, source FROM signals WHERE asset_id=? AND level=? AND name=? AND source != ?"
        args: list[Any] = [self.asset["id"], level, name, self.analyser.name]
        if source:
            sql += " AND source=?"
            args.append(source)
        sql += " ORDER BY CASE source WHEN 'fusion' THEN 1 ELSE 0 END"
        return {r["target_id"]: loads(r["value"]) for r in self.db.q(sql, args)}

    # -------------------------------------------------------------- writes (buffered)
    def signal(self, level: str, target_id: int, name: str, value: Any, confidence: float | None = None) -> None:
        self.signals.append(Signal(level, target_id, name, value, None if confidence is None else float(round(confidence, 4))))

    def shot_signal(self, shot: ShotRow | int, name: str, value: Any, confidence: float | None = None) -> None:
        self.signal("shot", shot if isinstance(shot, int) else shot.id, name, value, confidence)

    def asset_signal(self, name: str, value: Any, confidence: float | None = None) -> None:
        self.signal("asset", self.asset["id"], name, value, confidence)

    def moment(self, m: Moment) -> None:
        self.moments.append(m)

    def vector(self, shot_id: int, space: str, vec: Any) -> None:
        self.vectors.append((shot_id, space, vec))


class Analyser:
    name: ClassVar[str]
    version: ClassVar[str]
    requires: ClassVar[tuple[str, ...]] = ()
    # Higher runs earlier. The fast lane (proxy, shots, thumbnails, embeddings)
    # makes new uploads searchable quickly; heavy models follow.
    priority: ClassVar[int] = 50
    # Which shared resource it occupies: 'cpu' work runs in parallel workers;
    # 'model' work (large local models) is serialised to keep memory bounded.
    resource: ClassVar[str] = "cpu"
    description: ClassVar[str] = ""

    def config(self, settings: "Settings") -> dict[str, Any]:
        """Settings that change the output. Part of the input key."""
        return {}

    def check(self, settings: "Settings") -> str | None:
        """Return a reason string if the analyser cannot run here."""
        return None

    def run(self, ctx: AnalysisContext) -> dict[str, Any]:
        raise NotImplementedError

    @property
    def ident(self) -> str:
        return f"{self.name}@{self.version}"

    def input_key(self, settings: "Settings", content_hash: str, upstream: dict[str, str]) -> str:
        h = hashlib.blake2b(digest_size=12)
        payload = {
            "content": content_hash, "name": self.name, "version": self.version,
            "config": self.config(settings), "available": self.check(settings) is None,
            "upstream": {k: upstream.get(k, "") for k in self.requires},
        }
        h.update(json.dumps(payload, sort_keys=True, default=str).encode())
        return h.hexdigest()
