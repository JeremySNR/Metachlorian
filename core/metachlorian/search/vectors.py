"""In-memory ANN index over the ``vectors`` table (usearch HNSW, Apache-2.0).

SQLite is the source of truth; this index is a cache that is synchronised by
row id and can be rebuilt at any time. Filtered queries use exact scoring over
the candidate set when it is small, and oversampled HNSW + post-filter when it
is large (usearch's Python API has no filter predicate).
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import numpy as np

from ..db import Database

log = logging.getLogger(__name__)

EXACT_LIMIT = 20_000


class VectorIndex:
    def __init__(self, db: Database, space: str, cache_dir: Path | None = None, dtype: str = "f16"):
        self.db = db
        self.space = space
        self.cache_dir = cache_dir
        self.dtype = dtype
        self.lock = threading.RLock()
        self.index = None
        self.dim: int | None = None
        self.watermark = 0          # highest vectors.id ingested
        self.keys: set[int] = set()          # shot ids present
        self.shot_of: dict[int, int] = {}    # vector row id -> shot id
        self.vids_of: dict[int, list[int]] = {}  # shot id -> vector row ids
        # Exact scoring store: int8-quantised unit vectors, one row per vector id.
        self._chunks: list[np.ndarray] = []
        self.mat: np.ndarray | None = None
        self.slot_of: dict[int, int] = {}
        self._loaded_once = False
        self._unsaved = 0

    def _new(self, dim: int):
        from usearch.index import Index

        return Index(ndim=dim, metric="cos", dtype=self.dtype, connectivity=16, expansion_add=128, expansion_search=96)

    # ------------------------------------------------------------------ persistence
    def _paths(self):
        if not self.cache_dir:
            return None
        d = Path(self.cache_dir)
        return d / f"{self.space}.usearch", d / f"{self.space}.i8.npy", d / f"{self.space}.meta.json"

    def _try_load(self) -> bool:
        import json

        paths = self._paths()
        if not paths or not all(p.exists() for p in paths):
            return False
        ip, mp, jp = paths
        try:
            meta = json.loads(jp.read_text())
            rows = self.db.q("SELECT id, shot_id FROM vectors WHERE space=? AND id<=? ORDER BY id", (self.space, meta["watermark"]))
            if len(rows) != meta["count"] or meta.get("dtype") != self.dtype:
                return False
            from usearch.index import Index

            self.index = Index.restore(str(ip), view=False)
            self.mat = np.load(mp, mmap_mode="r")
            if self.index is None or len(self.mat) != len(rows):
                self.index = None
                return False
            self._chunks = [self.mat]
            self.dim = meta["dim"]
            self.shot_of, self.vids_of, self.slot_of = {}, {}, {}
            for j, r in enumerate(rows):
                self.shot_of[r["id"]] = r["shot_id"]
                self.vids_of.setdefault(r["shot_id"], []).append(r["id"])
                self.slot_of[r["id"]] = j
            self.watermark = meta["watermark"]
            log.info("loaded %s vectors for %s from cache", len(rows), self.space)
            return True
        except Exception:
            log.exception("vector cache unreadable; rebuilding")
            self.index = None
            return False

    def save(self) -> None:
        import json

        paths = self._paths()
        if not paths or self.index is None or self.mat is None:
            return
        ip, mp, jp = paths
        ip.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.index.save(str(ip) + ".tmp")
            np.save(str(mp) + ".tmp.npy", np.asarray(self.mat))
            os.replace(str(ip) + ".tmp", ip)
            os.replace(str(mp) + ".tmp.npy", mp)
            jp.write_text(json.dumps({"watermark": self.watermark, "count": len(self.shot_of), "dim": self.dim, "dtype": self.dtype}))

    def sync(self) -> int:
        """Pull new rows; rebuild when rows were deleted (re-analysis replaces them).

        Index keys are ``vectors.id``; ``self.shot_of`` maps them to shot ids, so a
        space may hold several vectors per shot (e.g. one per keyframe)."""
        with self.lock:
            if self.index is None and not self._loaded_once:
                self._loaded_once = True
                self._try_load()
            stat = self.db.q1("SELECT COUNT(*) n FROM vectors WHERE space=? AND id<=?", (self.space, self.watermark))
            if self.index is not None and stat["n"] != len(self.shot_of):
                self.index, self.shot_of, self.vids_of, self.watermark = None, {}, {}, 0
                self._chunks, self.mat, self.slot_of = [], None, {}
            added = 0
            while True:
                rows = self.db.q("SELECT id, shot_id, dim, vec FROM vectors WHERE space=? AND id>? ORDER BY id LIMIT 20000", (self.space, self.watermark))
                if not rows:
                    break
                if self.index is None:
                    self.dim = rows[0]["dim"]
                    self.index = self._new(self.dim)
                keys = np.array([r["id"] for r in rows], dtype=np.uint64)
                vecs = np.stack([np.frombuffer(r["vec"], dtype=np.float16).astype(np.float32) for r in rows])
                self.index.add(keys, vecs)
                unit = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
                base = sum(len(c) for c in self._chunks)
                self._chunks.append(np.clip(np.rint(unit * 127), -127, 127).astype(np.int8))
                for j, r in enumerate(rows):
                    self.slot_of[r["id"]] = base + j
                for r in rows:
                    self.shot_of[r["id"]] = r["shot_id"]
                    self.vids_of.setdefault(r["shot_id"], []).append(r["id"])
                self.watermark = rows[-1]["id"]
                added += len(rows)
            self.keys = set(self.vids_of)
            if added:
                self.mat = np.concatenate(self._chunks) if len(self._chunks) > 1 else self._chunks[0]
                self._chunks = [self.mat]
                self._unsaved += added
                if self._unsaved >= 20_000:
                    try:
                        self.save()
                        self._unsaved = 0
                    except Exception:  # pragma: no cover
                        log.exception("could not save the vector cache")
            return added

    def __len__(self) -> int:
        return len(self.keys)

    def vector_ids(self, shot_ids: list[int]) -> tuple[list[int], list[int]]:
        vids: list[int] = []
        sids: list[int] = []
        for s in shot_ids:
            for v in self.vids_of.get(s, ()):
                vids.append(v)
                sids.append(s)
        return vids, sids

    def get(self, vector_ids: list[int]) -> np.ndarray:
        """Unit vectors (dequantised int8) for vector row ids."""
        with self.lock:
            if self.mat is None or not vector_ids:
                return np.zeros((0, self.dim or 1), np.float32)
            slots = np.fromiter((self.slot_of[v] for v in vector_ids), dtype=np.int64, count=len(vector_ids))
            return self.mat[slots].astype(np.float32) / 127.0

    def shot_vector(self, shot_id: int) -> np.ndarray | None:
        vids, _ = self.vector_ids([shot_id])
        if not vids:
            return None
        v = self.get(vids).mean(axis=0)
        return v / (np.linalg.norm(v) + 1e-9)

    def search(self, q: np.ndarray, k: int, candidates: set[int] | None = None) -> list[tuple[int, float]]:
        """Top-k (shot_id, cosine) with the best vector per shot, optionally
        restricted to candidate shot ids."""
        with self.lock:
            if self.index is None or not self.shot_of:
                return []
            q = (q / (np.linalg.norm(q) + 1e-9)).astype(np.float32)
            if candidates is not None:
                if len(candidates) <= EXACT_LIMIT:
                    vids, sids = self.vector_ids(list(candidates))
                    if not vids:
                        return []
                    slots = np.fromiter((self.slot_of[v] for v in vids), dtype=np.int64, count=len(vids))
                    sims = (self.mat[slots] @ (q * 127).astype(np.float32)) / (127.0 * 127.0)
                    return _best_per_shot(sids, sims, k)
                over = max(k * 10, 1000)
                while True:
                    res = self.index.search(q, min(over, len(self.shot_of)))
                    sids = [self.shot_of.get(int(key), -1) for key in res.keys]
                    sims = 1.0 - np.asarray(res.distances, dtype=np.float32)
                    keep = [i for i, s in enumerate(sids) if s in candidates]
                    out = _best_per_shot([sids[i] for i in keep], sims[keep], k)
                    if len(out) >= k or over >= len(self.shot_of):
                        return out
                    over *= 4
            res = self.index.search(q, min(k * 3, len(self.shot_of)))
            sids = [self.shot_of.get(int(key), -1) for key in res.keys]
            return _best_per_shot(sids, 1.0 - np.asarray(res.distances, dtype=np.float32), k)


def _best_per_shot(sids: list[int], sims: np.ndarray, k: int) -> list[tuple[int, float]]:
    best: dict[int, float] = {}
    for s, v in zip(sids, sims.tolist()):
        if s >= 0 and v > best.get(s, -2.0):
            best[s] = v
    return sorted(best.items(), key=lambda x: -x[1])[:k]


class VectorStore:
    """One VectorIndex per embedding space, lazily created."""

    def __init__(self, db: Database, cache_dir: Path | None = None, dtype: str = "f16"):
        self.db = db
        self.dtype = dtype
        self.cache_dir = cache_dir
        self.spaces: dict[str, VectorIndex] = {}
        self.lock = threading.Lock()

    def get(self, space: str) -> VectorIndex:
        with self.lock:
            if space not in self.spaces:
                self.spaces[space] = VectorIndex(self.db, space, self.cache_dir, self.dtype)
            idx = self.spaces[space]
        idx.sync()
        return idx
