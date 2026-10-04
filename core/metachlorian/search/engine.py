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

SELECTIVE = 50_000
POOL = 600
RRF_K = 60
WEIGHTS = {"vector": 1.0, "keyword": 0.9, "terms": 1.1, "people": 0.5, "quality": 0.15, "example": 1.4}
TERM_MIN_CONF = 0.3
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
    vector: list[float] | None = None           # query-by-example embedding (image/clip)
    limit: int = 40
    cursor: str | None = None
    strict: bool = False                        # promote parsed preferences to hard filters
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


class SearchEngine:
    def __init__(self, db: Database, settings: Settings, vectors: VectorStore | None = None):
        self.db = db
        self.settings = settings
        self.vectors = vectors or VectorStore(db, settings.index_dir)

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
            if sid:
                v = self.vectors.get("visual").shot_vector(sid["id"])
                if v is not None:
                    res = self.vectors.get("visual").search(v, POOL + 1, candidates)
                    lists["example"] = [(s, sc) for s, sc in res if s != sid["id"]]
        if sem_text:
            qvec = self._text_vector(sem_text)
            if qvec is not None:
                lists["vector"] = self.vectors.get("visual").search(qvec, POOL, candidates)
        timings["vector"] = time.perf_counter() - t1
        t1 = time.perf_counter()
        kw = list(parsed.keywords) + [w for p in parsed.place for w in p.split()]
        if parsed.context:
            kw += [w for w in re.findall(r"\w+", parsed.context) if len(w) > 2]
        if not req.parse_query and req.q:
            kw = req.q.split()
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
                score = {}
                for r in self.db.q(f"SELECT shot_id, vocab, MAX(confidence) c FROM shot_terms WHERE ({cond}) AND confidence >= ?"
                                   f" GROUP BY shot_id, vocab ORDER BY c DESC LIMIT {POOL * 8}", (*pargs, TERM_MIN_CONF)):
                    score[r[0]] = score.get(r[0], 0) + r[2]
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
                rows = self.db.q(f"SELECT si.shot_id, IFNULL(si.quality, 0.5) q {base_from} WHERE {where} ORDER BY si.asset_id DESC, si.start_s LIMIT 5000", args)
                lists["quality"] = [(r[0], r[1]) for r in rows]
        # ---------------------------------------------------------- fuse
        fused: dict[int, float] = {}
        contrib: dict[int, dict[str, Any]] = {}
        for name, lst in lists.items():
            wgt = WEIGHTS.get(name, 1.0)
            for rank, (sid, sc) in enumerate(lst):
                fused[sid] = fused.get(sid, 0.0) + wgt / (RRF_K + rank + 1)
                contrib.setdefault(sid, {})[name] = {"rank": rank + 1, "score": round(float(sc), 4)}
        pool = list(fused)
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
        timings["fuse"] = time.perf_counter() - t1
        # ---------------------------------------------------------- page
        key = json.dumps([req.q, filters, require, exclude, prefer, intended, req.similar_to], sort_keys=True, default=str)[:400]
        offset = _dec_cursor(req.cursor, key)
        page = pool[offset: offset + limit]
        results = [self._result(sid, info.get(sid), contrib.get(sid, {}), fused[sid], snippets.get(sid), verdicts.get(sid), prefer, filters, kw)
                   for sid in page]
        facets = self._facets(pool if (lists and not (len(lists) == 1 and "quality" in lists)) else (list(candidates) if candidates is not None else None),
                              where, args, base_from) if req.facets else {}
        timings["total"] = time.perf_counter() - t0
        return {
            "query": {"text": req.q, "parsed": parsed.as_dict(), "filters": {k: v for k, v in filters.items() if not k.startswith("_")},
                      "require": require, "exclude": exclude, "prefer": prefer, "intended_use": intended or None, "limit": limit},
            "total": len(pool), "results": results, "facets": facets, "notes": notes,
            "excluded_by_rights": excluded_by_rights,
            "next_cursor": _enc_cursor(offset + limit, key) if offset + limit < len(pool) else None,
            "timings_ms": {k: round(v * 1000, 1) for k, v in timings.items()},
        }

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
            ids = pool[:20000]
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
