"""Search relevance evaluation with pooled human judgments.

1. `pool`: run every query through several ranking variants (hybrid default,
   visual vectors only, keywords only, hybrid without vocabulary preferences),
   pool the top-10 of each and render a numbered contact sheet per query for a
   judge. Writes pool.json.
2. A judge writes judgments.json: {query: {shot_key: grade}} with grades
   2 = exactly what was asked, 1 = partly relevant, 0 = not relevant.
   Shot keys are "filename@mid-time" so they survive re-segmentation.
3. `score`: nDCG@10 and P@5 (grade >= 1) per variant.

usage: python relevance.py pool <library> <out_dir>
       python relevance.py score <library> <out_dir>
"""
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from metachlorian.config import load_settings  # noqa: E402
from metachlorian.db import Database  # noqa: E402
from metachlorian.search import engine as E  # noqa: E402

QUERIES = [
    "drone shot of a coastline", "aerial view over houses and trees", "people dancing", "food market with vegetables",
    "crowd crossing the street", "close-up of food cooking in a pan", "man talking to the camera", "night concert on stage",
    "sunset over the sea", "snowy town by a river", "wild animals in nature", "boxing training in a gym",
    "driving along a road with palm trees", "aurora in the night sky", "people on a roller coaster",
    "interview with a sports player", "walking through a supermarket aisle", "lava eruption at night",
    "classroom with students sitting at desks", "timelapse of plants growing", "news presenter in a studio",
    "title card with text on black", "waves crashing on rocks", "handheld walk along a pier",
]
VARIANTS = ("hybrid", "visual_only", "keyword_only", "no_prefs")


def run_variant(eng: E.SearchEngine, q: str, variant: str, k: int = 10) -> list[int]:
    if variant == "hybrid":
        r = eng.search(E.SearchRequest(q=q, limit=k, facets=False))
    elif variant == "no_prefs":
        r = eng.search(E.SearchRequest(q=q, limit=k, facets=False, strict=False))
        # Drop the vocabulary preference list by re-running with parsing but no prefs.
        saved = E.WEIGHTS["terms"]
        E.WEIGHTS["terms"] = 0.0
        try:
            r = eng.search(E.SearchRequest(q=q, limit=k, facets=False))
        finally:
            E.WEIGHTS["terms"] = saved
    elif variant == "visual_only":
        v = eng._text_vector(q)
        return [s for s, _ in eng.vectors.get("visual").search(v, k)] if v is not None else []
    elif variant == "keyword_only":
        fq = E.fts_query(q.split())
        rows = eng.db.q("SELECT rowid FROM shot_fts WHERE shot_fts MATCH ? ORDER BY bm25(shot_fts) LIMIT ?", (fq, k)) if fq else []
        return [r[0] for r in rows]
    return [x["uid"] and eng.db.q1("SELECT id FROM shots WHERE uid=?", (x["uid"],))["id"] for x in r["results"]]


def key_of(db: Database, sid: int) -> str:
    r = db.q1("SELECT a.filename, s.start_s, s.end_s FROM shots s JOIN assets a ON a.id=s.asset_id WHERE s.id=?", (sid,))
    return f"{r['filename']}@{(r['start_s'] + r['end_s']) / 2:.2f}"


def thumb(lib: Path, db: Database, sid: int) -> np.ndarray:
    r = db.q1("SELECT a.uid, s.idx FROM shots s JOIN assets a ON a.id=s.asset_id WHERE s.id=?", (sid,))
    p = lib / "media" / r["uid"] / "kf" / f"{r['idx']:05d}_thumb.jpg"
    img = cv2.imread(str(p)) if p.exists() else None
    return cv2.resize(img, (288, 162)) if img is not None else np.zeros((162, 288, 3), np.uint8)


def main():
    cmd, lib, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("METACHLORIAN_MODELS", str(lib / "models"))
    s = load_settings(lib)
    db = Database(s.db_path)
    eng = E.SearchEngine(db, s)
    if cmd == "pool":
        pool = {}
        for qi, q in enumerate(QUERIES):
            ids: list[int] = []
            per = {}
            for v in VARIANTS:
                res = run_variant(eng, q, v)
                per[v] = [key_of(db, i) for i in res]
                ids += [i for i in res if i not in ids]
            keys = [key_of(db, i) for i in ids]
            pool[q] = {"keys": keys, "runs": per}
            tiles = []
            for n, i in enumerate(ids):
                t = thumb(lib, db, i).copy()
                cv2.rectangle(t, (0, 0), (40, 24), (0, 0, 0), -1)
                cv2.putText(t, str(n), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                tiles.append(t)
            while len(tiles) % 6:
                tiles.append(np.zeros((162, 288, 3), np.uint8))
            rows = [np.hstack(tiles[r:r + 6]) for r in range(0, len(tiles), 6)]
            sheet = np.vstack(rows)
            head = np.zeros((40, sheet.shape[1], 3), np.uint8)
            cv2.putText(head, f"Q{qi}: {q}", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.imwrite(str(out / f"q{qi:02d}.jpg"), np.vstack([head, sheet]), [cv2.IMWRITE_JPEG_QUALITY, 80])
        (out / "pool.json").write_text(json.dumps(pool, indent=1))
        print(f"pooled {len(QUERIES)} queries")
    elif cmd == "score":
        pool = json.loads((out / "pool.json").read_text())
        judg = json.loads((Path(__file__).with_name("judgments.json")).read_text())
        res = {}
        for v in VARIANTS:
            nd, p5 = [], []
            for q in QUERIES:
                grades = judg.get(q, {})
                ranked = run_variant(eng, q, v)
                g = [grades.get(key_of(db, i), 0) for i in ranked][:10]
                dcg = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(g))
                ideal = sorted(grades.values(), reverse=True)[:10]
                idcg = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(ideal)) or 1.0
                nd.append(dcg / idcg)
                p5.append(sum(1 for x in g[:5] if x >= 1) / 5)
            res[v] = {"ndcg@10": round(float(np.mean(nd)), 3), "p@5": round(float(np.mean(p5)), 3)}
        print(json.dumps(res, indent=1))
        (out / "scores.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
