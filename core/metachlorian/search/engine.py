"""Hybrid shot search: structured filters + keyword (FTS5/BM25) + semantic
(SigLIP vectors) + vocabulary preferences, fused with weighted reciprocal rank
fusion, rights-aware, with per-result explanations and facet counts.

Execution adapts to filter selectivity:
* selective filters (<= 50k shots): filter first, then score candidates
  exactly (vector cosine over the candidate set, FTS restricted to it);
* broad or no filters: retrieve pools from each retriever (ANN, FTS, top
  term matches), then apply the hard filters to the pool in SQL.
"""
from __future__ import annotations

import base64
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .. import rights as R
from ..config import Settings
from ..db import Database, loads
from ..vocab import registry
from .parse import Parsed, parse
from .vectors import VectorStore

SELECTIVE = 20_000
POOL_CAP = 4000
COMMON_DF = 0.08  # keyword tokens in more than 8% of shots carry little signal and cost the most
POOL = 600
RRF_K = 60
# Weights were set from pooled relevance judgments and known-item tests (eval/README.md, ADR 016):
# "exact" (every query word literally said, written on screen or in the place/file name) is the
# strongest evidence; vocabulary preferences are a gentle nudge because CPU-tier labels are noisy
# and the list is ordered by label confidence, not by relevance to the whole query.
WEIGHTS = {"vector": 1.0, "text": 0.8, "keyword": 0.9, "exact": 2.0, "terms": 0.3, "people": 0.5, "quality": 0.15, "example": 1.4}
EXACT_MAX_SHARE = 0.02  # an all-words match shared by more than 2% of shots is not specific evidence
STOPWORDS = frozenset("a an and are as at be but by for from has have in is it its of on or that the this to was were with".split())
TERM_MIN_CONF = 0.3
FUSE_TEXT_SPACE = False
BLOCKED_BADGES = frozenset({"not_cleared", "expired"})
# Match strength (0..1) thresholds. For text queries strength is SigLIP's own sigmoid probability on a
# log scale (p = 1e-4 -> 0, 1e-3 -> 0.25, 1e-2 -> 0.5, 0.1 -> 0.75); against blind judgments, precision
# (grade >= 1) is ~0.55 at loose, ~0.7 at balanced and ~0.85 at strict (eval/README.md).
EXACT_LIMIT_STRENGTH = 5000
STRENGTH_THRESHOLDS = {"loose": 0.25, "balanced": 0.4, "strict": 0.6}  # kept switchable for the relevance evaluation (eval/search)
FACET_VOCABS = ("shot_size", "camera_movement", "shot_role", "setting", "time_of_day", "weather", "pace", "mood", "audio_class",
                "edit_type", "resolution", "orientation", "look", "object", "concept", "quality_flag")
FTS_COLS_WEIGHTS = (1.0, 0.8, 0.9, 1.2, 1.6, 0.5)  # caption, transcript, ocr, tags, place, filename


@dataclass
class SearchRequest:
    q: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    require: dict[str, list[str]] = field(default_factory=dict)
    exclude: dict[str, list[str]] = field(default_factory=dict)
    prefer: dict[str, list[str]] = field(default_factory=dict)
    intended_use: dict[str, Any] | None = None   # {use, channel, territory, date, include: [...]}
    asset_uids: list[str] | None = None
    similar_to: str | None = None               # shot uid
    similar_space: str = "visual"               # visual | audio | text
    vector: list[float] | None = None           # query-by-example embedding (image/clip)
    limit: int = 40
    cursor: str | None = None
    strict: bool = False                        # promote parsed preferences to hard filters
    hide_blocked: bool = True                   # not cleared or expired: blocked for every use, hidden unless asked
    strictness: str = "balanced"                # loose | balanced | strict: where "strong" matches end
    facets: bool = True
    parse_query: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SearchRequest":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def _enc_cursor(offset: int, key: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset, "k": key}).encode()).decode().rstrip("=")


def _dec_cursor(c: str | None, key: str) -> int:
    if not c:
        return 0
    try:
        d = json.loads(base64.urlsafe_b64decode(c + "=" * (-len(c) % 4)))
        return int(d["o"]) if d.get("k") == key else 0
    except Exception:
        return 0


def fts_query(words: list[str]) -> str:
    toks = []
    for w in words:
        w = re.sub(r"[^\w]", "", w.lower())
        if len(w) >= 2:
            toks.append(f'"{w}"*' if len(w) >= 4 else f'"{w}"')
    return " OR ".join(dict.fromkeys(toks))


def fts_all_query(words: list[str]) -> str:
    """All words (prefix-matched), restricted to recorded evidence: what was said, written on screen,
    or named in the place and file name — not generated captions or labels."""
    toks = []
    for w in words:
        w = re.sub(r"[^\w]", "", w.lower())
        if len(w) >= 2 and w not in STOPWORDS:
            toks.append(f'"{w}"*' if len(w) >= 4 else f'"{w}"')
    toks = list(dict.fromkeys(toks))
    return "{transcript ocr place filename} : (" + " AND ".join(toks) + ")" if len(toks) >= 2 else ""


class SearchEngine:
    def __init__(self, db: Database, settings: Settings, vectors: VectorStore | None = None):
        self.db = db
        self.settings = settings
        self.vectors = vectors or VectorStore(db, settings.index_dir, settings.vector_dtype)

    # ------------------------------------------------------------------ helpers
    def _text_vector(self, text: str) -> np.ndarray | None:
        from .. import models
        from ..media import siglip

        if not text.strip() or not models.installed(self.settings.resolved_models_dir, "siglip-base-multilingual"):
            return None
        return siglip.text_vector(str(self.settings.resolved_models_dir), text)

    def _filter_sql(self, f: dict[str, Any], require: dict[str, list[str]], exclude: dict[str, list[str]],
                    asset_ids: list[int] | None) -> tuple[str, list[Any]]:
        reg = registry()
        where = ["a.deleted_at IS NULL"]
        args: list[Any] = []
        num = {"min_duration": ("si.duration >= ?", float), "max_duration": ("si.duration <= ?", float),
               "min_fps": ("si.fps >= ?", float), "max_fps": ("si.fps <= ?", float),
               "min_people": ("si.people_count >= ?", int), "max_people": ("IFNULL(si.people_count, 0) <= ?", int),
               "min_quality": ("si.quality >= ?", float)}
        for k, (sql, cast) in num.items():
            if f.get(k) is not None:
                where.append(sql)
                args.append(cast(f[k]))
        if f.get("min_height") is not None:
            where.append("MIN(si.width, si.height) >= ?")
            args.append(int(f["min_height"] * 0.95))
        if f.get("orientation"):
            where.append({"vertical": "si.height > si.width", "horizontal": "si.width > si.height",
                          "square": "ABS(si.width - si.height) < 4"}.get(f["orientation"], "1"))
        for k, col in (("log", "si.log_profile"), ("hdr", "si.hdr"), ("usable", "si.usable"), ("speech", "si.speech"), ("music", "si.music")):
            if f.get(k) is not None:
                where.append(f"IFNULL({col}, 0) = ?")
                args.append(int(bool(f[k])))
        if f.get("edit_type"):
            vals = f["edit_type"] if isinstance(f["edit_type"], list) else [f["edit_type"]]
            where.append(f"si.edit_type IN ({','.join('?' * len(vals))})")
            args += vals
        if f.get("captured_after"):
            where.append("si.capture_date >= ?")
            args.append(str(f["captured_after"]))
        if f.get("captured_before"):
            where.append("si.capture_date <= ?")
            args.append(str(f["captured_before"]))
        if asset_ids is not None:
            where.append(f"si.asset_id IN ({','.join('?' * len(asset_ids)) or 'NULL'})")
            args += asset_ids
        for vocab, terms in require.items():
            exp = sorted({t2 for t in terms for t2 in (reg.get(vocab).narrower(t) if vocab in reg.vocabs and t in reg.get(vocab).terms else {t})})
            where.append(f"EXISTS (SELECT 1 FROM shot_terms st WHERE st.shot_id=si.shot_id AND st.vocab=? AND st.term IN ({','.join('?' * len(exp))})"
                         f" AND st.confidence >= ?)")
            args += [vocab, *exp, TERM_MIN_CONF]
        for vocab, terms in exclude.items():
            exp = sorted({t2 for t in terms for t2 in (reg.get(vocab).narrower(t) if vocab in reg.vocabs and t in reg.get(vocab).terms else {t})})
            where.append(f"NOT EXISTS (SELECT 1 FROM shot_terms st WHERE st.shot_id=si.shot_id AND st.vocab=? AND st.term IN ({','.join('?' * len(exp))})"
                         f" AND st.confidence >= 0.5)")
            args += [vocab, *exp]
        return " AND ".join(where), args

    def _has_hard(self, f, require, exclude, asset_ids) -> bool:
        return bool([k for k, v in f.items() if v is not None]) or bool(require) or bool(exclude) or asset_ids is not None

    # ------------------------------------------------------------------ main
    def search(self, req: SearchRequest) -> dict[str, Any]:
        t0 = time.perf_counter()
        timings: dict[str, float] = {}
        parsed = parse(req.q) if (req.q and req.parse_query) else Parsed(text=req.q, semantic=req.q, keywords=req.q.split())
        filters = {**parsed.filters, **{k: v for k, v in req.filters.items() if v is not None}}
        prefer = {k: list(v) for k, v in parsed.prefer.items()}
        for k, v in req.prefer.items():
            prefer.setdefault(k, []).extend(t for t in v if t not in prefer.get(k, []))
        require = {k: list(v) for k, v in req.require.items()}
        exclude = {k: list(v) for k, v in parsed.exclude.items()}
        for k, v in req.exclude.items():
            exclude.setdefault(k, []).extend(v)
        if req.strict:
            for k, v in prefer.items():
                require.setdefault(k, []).extend(v)
            prefer = {}
        if "edit_type" in prefer and "edit_type" not in filters and req.strict:
            filters["edit_type"] = prefer.pop("edit_type")
        intended = dict(req.intended_use or {})
        if parsed.rights and not intended:
            intended = dict(parsed.rights)
        limit = max(1, min(200, req.limit if req.limit else (parsed.limit or 40)))
        if parsed.limit and not req.cursor and req.limit == 40:
            limit = parsed.limit
        asset_ids = None
        if req.asset_uids:
            asset_ids = [r["id"] for r in self.db.q(f"SELECT id FROM assets WHERE uid IN ({','.join('?' * len(req.asset_uids))})", req.asset_uids)]
        where, args = self._filter_sql(filters, require, exclude, asset_ids)
        base_from = "FROM shot_index si JOIN assets a ON a.id = si.asset_id"
        hard = self._has_hard(filters, require, exclude, asset_ids)
        candidates: set[int] | None = None
        if hard:
            rows = self.db.q(f"SELECT si.shot_id {base_from} WHERE {where} LIMIT {SELECTIVE + 1}", args)
            if len(rows) <= SELECTIVE:
                candidates = {r[0] for r in rows}
        timings["filter"] = time.perf_counter() - t0
        notes = list(parsed.notes)
        # Place: hard when anything matches it, otherwise a note.
        place_ids: set[int] | None = None
        if parsed.place:
            pq = " OR ".join(f'place:"{p}" OR caption:"{p}" OR ocr:"{p}" OR filename:"{p}"' for p in parsed.place)
            try:
                place_ids = {r[0] for r in self.db.q("SELECT rowid FROM shot_fts WHERE shot_fts MATCH ? LIMIT 100000", (pq,))}
            except Exception:
                place_ids = set()
            if place_ids:
                candidates = place_ids if candidates is None and not hard else (candidates & place_ids if candidates is not None else None)
                if candidates is None:
                    filters["_place_ids"] = True
            else:
                notes.append(f"Nothing in the library is tagged or described with {', '.join(parsed.place)}; showing the closest matches instead.")
        # ---------------------------------------------------------- retrievers
        lists: dict[str, list[tuple[int, float]]] = {}
        sem_text = parsed.semantic if req.parse_query else req.q
        qvec = None
        t1 = time.perf_counter()
        if req.vector is not None:
            qvec = np.asarray(req.vector, dtype=np.float32)
            lists["example"] = self.vectors.get("visual").search(qvec, POOL, candidates)
        elif req.similar_to:
            sid = self.db.q1("SELECT id FROM shots WHERE uid=?", (req.similar_to,))
            space = req.similar_space if req.similar_space in ("visual", "audio", "text") else "visual"
            if sid:
                v = self.vectors.get(space).shot_vector(sid["id"])
                if v is not None:
                    res = self.vectors.get(space).search(v, POOL + 1, candidates)
                    lists["example"] = [(s, sc) for s, sc in res if s != sid["id"]]
        if sem_text:
            qvec = self._text_vector(sem_text)
            if qvec is not None:
                lists["vector"] = self.vectors.get("visual").search(qvec, POOL, candidates)
                # The "text" space (SigLIP text tower over transcript + caption + OCR) is not fused here:
                # pooled judgments showed it is a poor sentence matcher (nDCG@10 0.58 -> 0.73 without it,
                # eval/README.md). Spoken and written words are matched by BM25 below; the text space
                # stays available for "similar by transcript" (similar_space="text").
                if FUSE_TEXT_SPACE:
                    tl = self.vectors.get("text").search(qvec, POOL, candidates)
                    if tl:
                        lists["text"] = [(s, sc) for s, sc in tl if sc >= 0.35]
        timings["vector"] = time.perf_counter() - t1
        t1 = time.perf_counter()
        kw = list(parsed.keywords) + [w for p in parsed.place for w in p.split()]
        if parsed.context:
            kw += [w for w in re.findall(r"\w+", parsed.context) if len(w) > 2]
        if not req.parse_query and req.q:
            kw = req.q.split()
        kw = self._prune_common(kw)
        fq = fts_query(kw)
        snippets: dict[int, dict[str, str]] = {}
        if fq:
            w = ",".join(str(x) for x in FTS_COLS_WEIGHTS)
            try:
                rows = self.db.q(f"SELECT rowid, bm25(shot_fts, {w}) s, snippet(shot_fts, 1, '[', ']', '…', 10) tr,"
                                 f" snippet(shot_fts, 0, '[', ']', '…', 10) cap, snippet(shot_fts, 2, '[', ']', '…', 8) ocr"
                                 f" FROM shot_fts WHERE shot_fts MATCH ? ORDER BY s LIMIT {POOL * 3}", (fq,))
            except Exception:
                rows = []
            kl = []
            for r in rows:
                if candidates is not None and r[0] not in candidates:
                    continue
                kl.append((r[0], -float(r[1])))
                snippets[r[0]] = {k: r[k] for k in ("tr", "cap", "ocr") if r[k] and "[" in r[k]}
            lists["keyword"] = kl[:POOL]
        if req.q and req.parse_query:
            aq = fts_all_query(re.findall(r"[\w']+", parsed.text or req.q))
            if aq:
                try:
                    rows = self.db.q(f"SELECT rowid, bm25(shot_fts) s FROM shot_fts WHERE shot_fts MATCH ? ORDER BY s LIMIT {POOL}", (aq,))
                except Exception:
                    rows = []
                if rows and len(rows) <= max(50, EXACT_MAX_SHARE * self._shot_count()):
                    lists["exact"] = [(r[0], -float(r[1])) for r in rows if candidates is None or r[0] in candidates]
        timings["keyword"] = time.perf_counter() - t1
        t1 = time.perf_counter()
        pref_pairs = [(v, t) for v, ts in prefer.items() for t in ts]
        if pref_pairs:
            reg = registry()
            expanded = []
            for v, t in pref_pairs:
                exp = reg.get(v).narrower(t) if v in reg.vocabs and t in reg.get(v).terms else {t}
                expanded += [(v, x) for x in exp]
            cond = " OR ".join("(vocab=? AND term=?)" for _ in expanded)
            pargs = [x for pair in expanded for x in pair]
            if candidates is not None:
                ids = list(candidates)
                score: dict[int, float] = {}
                for i in range(0, len(ids), 900):
                    chunk = ids[i:i + 900]
                    for r in self.db.q(f"SELECT shot_id, vocab, MAX(confidence) c FROM shot_terms WHERE ({cond}) AND shot_id IN ({','.join('?' * len(chunk))})"
                                       f" GROUP BY shot_id, vocab", (*pargs, *chunk)):
                        score[r[0]] = score.get(r[0], 0) + r[2]
            else:
                # Broad: best-confidence shots per preferred term via the (vocab, term, confidence) index.
                per_vocab: dict[tuple[int, str], float] = {}
                for v, t in expanded:
                    for r in self.db.q("SELECT shot_id, confidence FROM shot_terms WHERE vocab=? AND term=? AND confidence >= ?"
                                       " ORDER BY confidence DESC LIMIT ?", (v, t, TERM_MIN_CONF, POOL * 4)):
                        key = (r[0], v)
                        per_vocab[key] = max(per_vocab.get(key, 0.0), r[1])
                score = {}
                for (sid, _v), c in per_vocab.items():
                    score[sid] = score.get(sid, 0.0) + c
            lists["terms"] = sorted(score.items(), key=lambda x: -x[1])[:POOL * 2]
        timings["terms"] = time.perf_counter() - t1
        # Pure browse (no query): order candidates by quality.
        if not lists:
            if candidates is not None:
                ids = list(candidates)[:SELECTIVE]
                rows = []
                for i in range(0, len(ids), 900):
                    chunk = ids[i:i + 900]
                    rows += self.db.q(f"SELECT shot_id, IFNULL(quality, 0.5) q FROM shot_index WHERE shot_id IN ({','.join('?' * len(chunk))})", chunk)
                lists["quality"] = sorted(((r[0], r[1]) for r in rows), key=lambda x: -x[1])
            else:
                rows = self.db.q(f"SELECT si.shot_id, IFNULL(si.quality, 0.5) q {base_from} WHERE {where} ORDER BY a.id DESC, si.start_s LIMIT 5000", args)
                lists["quality"] = [(r[0], r[1]) for r in rows]
        # ---------------------------------------------------------- fuse
        fused: dict[int, float] = {}
        contrib: dict[int, dict[str, Any]] = {}
        for name, lst in lists.items():
            wgt = WEIGHTS.get(name, 1.0)
            for rank, (sid, sc) in enumerate(lst):
                fused[sid] = fused.get(sid, 0.0) + wgt / (RRF_K + rank + 1)
                contrib.setdefault(sid, {})[name] = {"rank": rank + 1, "score": round(float(sc), 4)}
        pool = sorted(fused, key=lambda x: -fused[x])[:POOL_CAP]
        # Hard filters on broad queries are applied to the pool now.
        if hard and candidates is None and pool:
            ok: set[int] = set()
            for i in range(0, len(pool), 900):
                chunk = pool[i:i + 900]
                ok |= {r[0] for r in self.db.q(f"SELECT si.shot_id {base_from} WHERE {where} AND si.shot_id IN ({','.join('?' * len(chunk))})",
                                               (*args, *chunk))}
            if place_ids:
                ok &= place_ids
            pool = [s for s in pool if s in ok]
        if not hard and candidates is None and place_ids:
            pool = [s for s in pool if s in place_ids]
        # Soft people preference and a light quality prior.
        info = self._load_index_rows(pool)
        if parsed.prefer_people:
            for sid in pool:
                pc = info.get(sid, {}).get("people_count") or 0
                if pc >= parsed.prefer_people:
                    fused[sid] += WEIGHTS["people"] / (RRF_K + 1)
                    contrib[sid]["people"] = {"count": pc}
        for sid in pool:
            q = info.get(sid, {}).get("quality")
            if q is not None:
                fused[sid] += WEIGHTS["quality"] * float(q) / (RRF_K + 1)
            if info.get(sid, {}).get("usable") == 0:
                fused[sid] *= 0.85
        pool.sort(key=lambda s: -fused[s])
        # ---------------------------------------------------------- rights
        verdicts: dict[int, dict[str, Any]] = {}
        excluded_by_rights = 0
        badges = self._badges(pool, info)
        hidden_blocked = 0
        if req.hide_blocked:
            # Blocked footage (not cleared, or past expiry) is blocked for every use, so it is hidden
            # whether or not an intended use was given.
            kept = [sid for sid in pool if badges.get(sid) not in BLOCKED_BADGES]
            hidden_blocked = len(pool) - len(kept)
            excluded_by_rights += hidden_blocked
            pool = kept
        if intended:
            include = set(intended.get("include") or ["allowed"])
            kept = []
            cache: dict[tuple[int, int | None], dict[str, Any]] = {}
            overrides = {(r["asset_id"], r["shot_id"]) for r in self.db.q("SELECT asset_id, shot_id FROM rights WHERE shot_id IS NOT NULL")}
            for sid in pool:
                row = info.get(sid)
                if not row:
                    continue
                key = (row["asset_id"], sid if (row["asset_id"], sid) in overrides else None)
                if key not in cache:
                    cache[key] = R.get_rights(self.db, key[0], key[1])
                v = R.check(cache[key], intended.get("use"), intended.get("channel"), intended.get("territory"), intended.get("date"),
                            people_visible=(row.get("people_count") or 0) > 0)
                verdicts[sid] = v
                if v["verdict"] in include:
                    kept.append(sid)
                else:
                    excluded_by_rights += 1
            pool = kept
        # ---------------------------------------------------------- strength: strong matches first
        evidence = self._word_evidence(snippets, kw)
        strength = self._strengths(pool, contrib, qvec if (sem_text and req.vector is None) else None,
                                   req.vector is not None or bool(req.similar_to), req.similar_space, evidence)
        threshold = STRENGTH_THRESHOLDS.get(req.strictness, STRENGTH_THRESHOLDS["balanced"])
        if strength:
            strong = [sid for sid in pool if (strength.get(sid) or 0) >= threshold]
            strong_set = set(strong)
            pool = strong + [sid for sid in pool if sid not in strong_set]
            strong_count = len(strong)
        else:
            strong_count = len(pool)
        timings["fuse"] = time.perf_counter() - t1
        # ---------------------------------------------------------- page
        key = json.dumps([req.q, filters, require, exclude, prefer, intended, req.similar_to, req.strictness, req.hide_blocked],
                         sort_keys=True, default=str)[:400]
        offset = _dec_cursor(req.cursor, key)
        page = pool[offset: offset + limit]
        results = [self._result(sid, info.get(sid), contrib.get(sid, {}), fused[sid], snippets.get(sid), verdicts.get(sid), prefer, filters, kw)
                   for sid in page]
        for r, sid in zip(results, page):
            r["rights_badge"] = badges.get(sid, "unknown")
            st = strength.get(sid) if strength else None
            r["strength"] = None if st is None else round(st, 3)
            r["strong"] = True if not strength else (st or 0) >= threshold
        # Facets describe the ranked pool (at most 5,000 shots), never the whole library: aggregating
        # terms over every match of a broad filter took minutes at 1.5M shots.
        facets = self._facets(pool, where, args, base_from) if req.facets else {}
        timings["total"] = time.perf_counter() - t0
        return {
            "query": {"text": req.q, "parsed": parsed.as_dict(), "filters": {k: v for k, v in filters.items() if not k.startswith("_")},
                      "require": require, "exclude": exclude, "prefer": prefer, "intended_use": intended or None, "limit": limit},
            "total": len(pool), "results": results, "facets": facets, "notes": notes,
            "excluded_by_rights": excluded_by_rights, "hidden_blocked": hidden_blocked,
            "strong_count": strong_count, "strictness": req.strictness if strength else None, "strength_thresholds": STRENGTH_THRESHOLDS,
            "next_cursor": _enc_cursor(offset + limit, key) if offset + limit < len(pool) else None,
            "timings_ms": {k: round(v * 1000, 1) for k, v in timings.items()},
        }

    @staticmethod
    def _word_evidence(snippets: dict[int, dict[str, str]], kw: list[str]) -> dict[int, float]:
        """Share of the query's keywords found in what was said or written on screen, per shot."""
        toks = {re.sub(r"[^\w]", "", w.lower()) for w in kw}
        toks = {t for t in toks if len(t) >= 2 and t not in STOPWORDS}
        if not toks:
            return {}
        out: dict[int, float] = {}
        for sid, sn in snippets.items():
            hits = {h.lower() for k in ("tr", "ocr") for h in re.findall(r"\[([^\]]+)\]", sn.get(k) or "")}
            found = sum(1 for t in toks if any(h.startswith(t[:max(4, len(t) - 2)]) or h == t for h in hits))
            if found:
                out[sid] = found / len(toks)
        return out

    def _strengths(self, pool: list[int], contrib: dict[int, dict[str, Any]], qvec: np.ndarray | None, by_example: bool,
                   space: str, evidence: dict[int, float] | None = None) -> dict[int, float]:
        """Absolute match strength per shot (0..1), comparable across queries. Empty when the query has no
        content to match (filter-only browse), in which case every result counts as strong."""
        if not pool:
            return {}
        out: dict[int, float] = {}
        if by_example:
            for sid in pool:
                ex = contrib.get(sid, {}).get("example")
                # Image-to-image cosine: ~0.55 is unrelated, ~0.95 near-identical (uncalibrated, monotonic).
                out[sid] = float(np.clip((ex["score"] - 0.55) / 0.4, 0, 1)) if ex else 0.0
            return out
        if qvec is None:
            if any("exact" in contrib.get(s, {}) or "keyword" in contrib.get(s, {}) for s in pool):
                ev = evidence or {}
                return {sid: (0.95 if "exact" in contrib.get(sid, {}) else 0.45 + 0.5 * ev[sid] if sid in ev else 0.0) for sid in pool}
            return {}
        from ..media import siglip

        enc = siglip.load(str(self.settings.resolved_models_dir))
        cos = dict(self.vectors.get("visual").search(qvec, len(pool), candidates=set(pool[:EXACT_LIMIT_STRENGTH])))
        for sid in pool:
            c = cos.get(sid)
            st = 0.0
            if c is not None:
                p = 1.0 / (1.0 + np.exp(-(c * enc.scale + enc.bias)))
                st = float(np.clip((np.log10(max(p, 1e-9)) + 4) / 4, 0, 1))
            if "exact" in contrib.get(sid, {}):
                st = max(st, 0.95)  # every query word said, written or named: strong evidence on its own
            elif evidence and sid in evidence:
                st = max(st, 0.45 + 0.5 * evidence[sid])  # some of the words were said or shown
            out[sid] = st
        return out

    def _badges(self, pool: list[int], info: dict[int, dict[str, Any]]) -> dict[int, str]:
        """Rights badge per shot (shot overrides win over the asset), in a few bulk queries."""
        aids = sorted({info[s]["asset_id"] for s in pool if s in info})
        asset_level: dict[int, tuple[str, str | None]] = {}
        shot_level: dict[int, tuple[str, str | None]] = {}
        for i in range(0, len(aids), 900):
            chunk = aids[i:i + 900]
            for r in self.db.q(f"SELECT asset_id, shot_id, status, expires FROM rights WHERE asset_id IN ({','.join('?' * len(chunk))})", chunk):
                if r["shot_id"] is None:
                    asset_level[r["asset_id"]] = (r["status"], r["expires"])
                else:
                    shot_level[r["shot_id"]] = (r["status"], r["expires"])
        out: dict[int, str] = {}
        for sid in pool:
            row = info.get(sid)
            if not row:
                continue
            st, exp = asset_level.get(row["asset_id"], ("unknown", None))
            if sid in shot_level:
                s_st, s_exp = shot_level[sid]
                st, exp = (s_st if s_st != "unknown" else st), (s_exp or exp)
            try:
                out[sid] = R.summary_status({"status": st, "expires": exp})
            except ValueError:
                out[sid] = st
        return out

    def _prune_common(self, words: list[str]) -> list[str]:
        """Drop keyword tokens that occur in a large share of shots (IDF pruning).
        They are expensive for BM25 over millions of rows and add little; the
        semantic retriever still sees the whole phrase."""
        if not words:
            return words
        total = self._shot_count()
        if total < 50_000:
            return words
        keep = []
        for w in words:
            t = re.sub(r"[^\w]", "", w.lower())
            r = self.db.q1("SELECT doc FROM shot_fts_vocab WHERE term=?", (t,))
            if r is None or r[0] / total <= COMMON_DF:
                keep.append(w)
        return keep

    def _shot_count(self) -> int:
        now_t = time.time()
        if not hasattr(self, "_count_cache") or now_t - self._count_cache[1] > 60:
            self._count_cache = (self.db.q1("SELECT COUNT(*) n FROM shot_index")["n"], now_t)
        return self._count_cache[0]

    def _load_index_rows(self, ids: list[int]) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for i in range(0, len(ids), 900):
            chunk = ids[i:i + 900]
            for r in self.db.q(f"SELECT shot_id, asset_id, people_count, quality, usable FROM shot_index WHERE shot_id IN ({','.join('?' * len(chunk))})", chunk):
                out[r[0]] = dict(r)
        return out

    def _result(self, sid: int, row, contrib, score, snip, verdict, prefer, filters, kw) -> dict[str, Any]:
        r = self.db.q1("SELECT doc FROM shot_index WHERE shot_id=?", (sid,))
        doc = loads(r["doc"]) if r else {}
        fields = doc.get("fields", {})
        reg = registry()
        why: list[dict[str, Any]] = []
        if "vector" in contrib:
            why.append({"signal": "visual similarity", "detail": f"looks like the description (similarity {contrib['vector']['score']:.2f}, rank {contrib['vector']['rank']})",
                        "score": contrib["vector"]["score"]})
        if "example" in contrib:
            why.append({"signal": "similar shot", "detail": f"visually similar to the example (similarity {contrib['example']['score']:.2f})",
                        "score": contrib["example"]["score"]})
        if "text" in contrib:
            why.append({"signal": "meaning of speech or description", "detail": f"what is said or described is close in meaning (similarity {contrib['text']['score']:.2f})",
                        "score": contrib["text"]["score"]})
        if "exact" in contrib:
            why.append({"signal": "exact words", "detail": "every word of the query was said, shown on screen or is in the place or file name"})
        if "keyword" in contrib:
            sn = snip or {}
            where_found = "transcript" if "tr" in sn else "caption" if "cap" in sn else "on-screen text" if "ocr" in sn else "tags or file name"
            why.append({"signal": "keywords", "detail": f"words matched in the {where_found}", "snippet": sn.get("tr") or sn.get("cap") or sn.get("ocr")})
        from ..records import VOCAB_FIELDS

        vocab_to_field = {v: k for k, (v, _) in VOCAB_FIELDS.items()}
        for vocab, terms in prefer.items():
            fname = vocab_to_field.get(vocab)
            val = fields.get(fname, {}).get("value") if fname else None
            items = val if isinstance(val, list) else [val] if isinstance(val, dict) else []
            for t in terms:
                exp = reg.get(vocab).narrower(t) if vocab in reg.vocabs and t in reg.get(vocab).terms else {t}
                hit = next((i for i in items if isinstance(i, dict) and i.get("term") in exp), None)
                if hit:
                    src = fields[fname].get("source")
                    why.append({"signal": vocab, "detail": f"{reg.label(vocab, hit['term'])} ({'corrected by a person' if src == 'human' else 'confidence ' + format(hit.get('confidence') or 0, '.2f')})",
                                "term": hit["term"], "confidence": hit.get("confidence"), "source": src})
                else:
                    why.append({"signal": vocab, "detail": f"not labelled {reg.label(vocab, t)}", "term": t, "missing": True})
        if "people" in contrib:
            why.append({"signal": "people", "detail": f"{contrib['people']['count']} people visible"})
        for k, v in filters.items():
            if k.startswith("_"):
                continue
            why.append({"signal": "filter", "detail": f"{k.replace('_', ' ')}: {v}", "filter": k})
        # Best in/out: the speech or text moment containing the keywords, else the whole shot.
        in_s, out_s = doc.get("start"), doc.get("end")
        moment = None
        if kw and doc.get("moments"):
            words = {w.lower() for w in kw if len(w) > 2}
            for m in doc["moments"]:
                if m["kind"] in ("speech", "text") and words & set(re.findall(r"\w+", (m.get("text") or "").lower())):
                    moment = m
                    in_s, out_s = max(doc["start"], m["start"] - 0.25), min(doc["end"], m["end"] + 0.25)
                    break
        out = summarise_doc(doc)
        out.update({"score": round(score, 5), "why": why, "in": round(in_s, 3) if in_s is not None else None,
                    "out": round(out_s, 3) if out_s is not None else None, "moment": moment})
        if verdict:
            out["rights"] = {"verdict": verdict["verdict"], "reasons": verdict["reasons"]}
        return out

    def _facets(self, pool: list[int] | None, where: str, args: list[Any], base_from: str) -> dict[str, list[dict[str, Any]]]:
        reg = registry()
        out: dict[str, list[dict[str, Any]]] = {}
        if pool is not None and not pool:
            return {}
        if pool is not None:
            ids = pool[:5000]
            counts: dict[tuple[str, str], int] = {}
            for i in range(0, len(ids), 900):
                chunk = ids[i:i + 900]
                for r in self.db.q(f"SELECT vocab, term, COUNT(*) n FROM shot_terms WHERE confidence >= 0.4 AND shot_id IN ({','.join('?' * len(chunk))})"
                                   f" GROUP BY vocab, term", chunk):
                    counts[(r[0], r[1])] = counts.get((r[0], r[1]), 0) + r[2]
        else:
            counts = {(r[0], r[1]): r[2] for r in self.db.q(
                f"SELECT st.vocab, st.term, COUNT(*) n FROM shot_terms st JOIN shot_index si ON si.shot_id=st.shot_id JOIN assets a ON a.id=si.asset_id"
                f" WHERE st.confidence >= 0.4 AND {where} GROUP BY st.vocab, st.term", args)}
        for (v, t), n in counts.items():
            if v not in FACET_VOCABS:
                continue
            out.setdefault(v, []).append({"term": t, "label": reg.label(v, t) if v in reg.vocabs else t.replace("_", " "), "count": n})
        for v in out:
            out[v].sort(key=lambda x: -x["count"])
            out[v] = out[v][:12 if v in ("object", "concept") else 20]
        return out


def summarise_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact shot record for result lists (full record via get_shot)."""
    f = doc.get("fields", {})

    def val(name):
        x = f.get(name, {}).get("value")
        if isinstance(x, dict):
            return x.get("value", x.get("term"))
        return x

    def terms(name, n=4):
        x = f.get(name, {}).get("value") or []
        if isinstance(x, dict):
            x = [x]
        return [{"term": i.get("term"), "confidence": i.get("confidence")} for i in x[:n] if isinstance(i, dict)]

    t = doc.get("technical", {})
    return {
        "uid": doc.get("uid"), "asset_uid": doc.get("asset_uid"), "filename": doc.get("filename"), "idx": doc.get("idx"),
        "start": doc.get("start"), "end": doc.get("end"), "duration": doc.get("duration"), "fps": t.get("fps"),
        "thumb": f"/media/{doc.get('asset_uid')}/{doc['thumb']}" if doc.get("thumb") else None,
        "poster": f"/media/{doc.get('asset_uid')}/{doc['poster']}" if doc.get("poster") else None,
        "proxy": f"/media/{doc.get('asset_uid')}/proxy.mp4",
        "caption": val("content.caption"), "summary": val("content.summary"),
        "shot_size": val("camera.shot_size"), "camera_movement": terms("camera.movement"), "role": terms("shot.role", 3),
        "setting": terms("content.setting", 3), "time_of_day": val("content.time_of_day"), "pace": val("pacing.pace"),
        "people": val("people.count"), "usable": val("quality.usable"),
        "resolution": f"{t.get('width')}x{t.get('height')}" if t.get("width") else None, "resolution_class": t.get("resolution_class"),
        "log_profile": t.get("log_profile"), "hdr": t.get("hdr"), "edit_type": (doc.get("edit_type") or {}).get("term") if isinstance(doc.get("edit_type"), dict) else doc.get("edit_type"),
        "corrected": sorted(k for k, v in f.items() if v.get("corrected")),
    }


_ = math
