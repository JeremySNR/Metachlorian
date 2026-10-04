"""Storage/search benchmark at library scale.

Builds a synthetic library of N shots (default 4.5 M = 10,000 hours at an
8 s average shot length) with realistic structure: vectors are perturbations of
real SigLIP shot embeddings taken from an indexed library, terms follow the
controlled vocabularies with skewed frequencies, captions and transcripts are
drawn from a word bank. Then runs typical hybrid queries through the real
SearchEngine (real SigLIP text encoding) and reports latency percentiles.

usage: python bench/storage_bench.py --out /path/bench-lib --shots 4500000 --seed-lib /path/demo-lib
"""
from __future__ import annotations

import argparse
import json
import os
import random
import resource
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from metachlorian.config import load_settings  # noqa: E402
from metachlorian.db import Database, dumps  # noqa: E402
from metachlorian.search.engine import SearchEngine, SearchRequest  # noqa: E402
from metachlorian.vocab import registry  # noqa: E402

WORDS = ("beach coast sea waves sunset city street market food stall people crowd night lights car road drone aerial mountain forest "
         "river boat harbour bridge tram building office meeting interview laptop hands coffee kitchen cooking family children holiday "
         "travel hotel pool airport train station festival concert music dance football stadium runner cyclist dog park garden rain "
         "snow fog morning evening lisbon porto london paris tokyo desert canyon lake island cliff lighthouse fishing village").split()
QUERIES = [
    ("slow wide drone shots of a coastline at golden hour, no people, at least 8 seconds, 4K", {}),
    ("handheld street food close-ups, busy, night", {}),
    ("family holiday on the beach", {}),
    ("interview in an office", {}),
    ("city traffic at night", {}),
    ("someone cooking in a kitchen", {}),
    ("aerial view of mountains", {}),
    ("people walking in a market", {}),
    ("", {"min_height": 2160, "min_fps": 50}),
    ("sunset over the sea", {"orientation": "vertical"}),
    ("football crowd", {"min_duration": 5}),
    ("rain in the street", {}),
    ("lisbon tram", {}),
    ("close-up of hands typing on a laptop", {"max_people": 1}),
    ("boat in a harbour", {"log": True}),
    ("festival concert lights", {"min_people": 4}),
]


def build(out: Path, n: int, seed_lib: Path, batch: int = 50_000) -> None:
    rng = np.random.default_rng(7)
    pyrng = random.Random(7)
    s = load_settings(out)
    s.ensure_dirs()
    db = Database(s.db_path)
    src = Database(seed_lib / "library.sqlite")
    seeds = np.stack([np.frombuffer(r["vec"], np.float16).astype(np.float32) for r in src.q("SELECT vec FROM vectors WHERE space='visual'")])
    seeds /= np.linalg.norm(seeds, axis=1, keepdims=True)
    print(f"{len(seeds)} seed vectors", flush=True)
    reg = registry()
    vocab_terms = {v: list(reg.get(v).terms) for v in ("shot_size", "camera_movement", "shot_role", "setting", "time_of_day", "weather", "pace", "mood")}
    conn = db.conn
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=OFF")
    shots_per_asset = 60
    t0 = time.time()
    sid = 0
    aid = 0
    while sid < n:
        conn.execute("BEGIN")
        rows_a, rows_s, rows_i, rows_t, rows_f, rows_v = [], [], [], [], [], []
        for _ in range(batch // shots_per_asset):
            aid += 1
            w, h = pyrng.choice([(3840, 2160), (1920, 1080), (1920, 1080), (1080, 1920), (1280, 720), (4096, 2160)])
            fps = pyrng.choice([23.976, 25, 29.97, 50, 59.94, 24])
            rows_a.append((aid, f"a{aid:010d}", f"/footage/{pyrng.choice(WORDS)}/{aid}.mov", f"{aid}.mov", 1_000_000, 0, f"q{aid}", f"h{aid}", "ready",
                           shots_per_asset * 8.0, w, h, fps, "{}", "{}", 0, 0, 0))
            t = 0.0
            for k in range(shots_per_asset):
                sid += 1
                d = float(rng.gamma(2.0, 4.0)) + 0.5
                rows_s.append((sid, f"a{aid:010d}-{k}", aid, k, t, t + d, int(t * fps), int((t + d) * fps), "shot", "cut", "x", "[]"))
                people = int(rng.choice([0, 0, 0, 1, 1, 2, 3, 5, 12]))
                cap_words = pyrng.sample(WORDS, 8)
                caption = " ".join(cap_words)
                tod = pyrng.choice(vocab_terms["time_of_day"])
                doc = {"uid": f"a{aid:010d}-{k}", "asset_uid": f"a{aid:010d}", "filename": f"{aid}.mov", "idx": k, "start": t, "end": t + d,
                       "duration": d, "technical": {"width": w, "height": h, "fps": fps}, "fields": {"content.caption": {"value": {"value": caption}}}}
                rows_i.append((sid, aid, d, t, t + d, w, h, fps, w / h, int(pyrng.random() < 0.1), int(pyrng.random() < 0.05), people, min(people, 3),
                               int(pyrng.random() < 0.3), int(pyrng.random() < 0.2), float(rng.random()), pyrng.choice(vocab_terms["pace"]),
                               pyrng.choice(vocab_terms["shot_size"]), pyrng.choice(vocab_terms["camera_movement"]), pyrng.choice(vocab_terms["shot_role"]),
                               tod, 1, float(rng.random()), None, None, pyrng.choice(["raw", "raw", "selects", "finished"]), caption, json.dumps(doc), 0))
                for v, terms in vocab_terms.items():
                    for term in pyrng.sample(terms, 1 if v in ("shot_size", "time_of_day", "pace") else 2):
                        rows_t.append((sid, v, term, round(float(rng.uniform(0.2, 0.99)), 3), "bench"))
                rows_f.append((sid, caption, " ".join(pyrng.choices(WORDS, k=12)) if pyrng.random() < 0.3 else "", "", " ".join(cap_words[:3]),
                               pyrng.choice(WORDS), f"{aid}"))
                base = seeds[pyrng.randrange(len(seeds))]
                vec = base + rng.normal(0, 0.025, base.shape)
                vec /= np.linalg.norm(vec)
                rows_v.append((sid, sid, aid, "visual", 768, vec.astype(np.float16).tobytes(), 0))
                t += d
        conn.executemany("INSERT INTO assets(id, uid, path, filename, size, mtime, quick_hash, content_hash, status, duration, width, height, fps, tech,"
                         " summary, priority, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows_a)
        conn.executemany("INSERT INTO shots(id, uid, asset_id, idx, start_s, end_s, start_frame, end_frame, kind, transition_in, segmenter, keyframes)"
                         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows_s)
        conn.executemany("INSERT INTO shot_index(shot_id, asset_id, duration, start_s, end_s, width, height, fps, aspect, log_profile, hdr, people_count,"
                         " faces, speech, music, motion_energy, pace, shot_size, camera_movement, role, time_of_day, usable, quality, capture_date,"
                         " location, edit_type, caption, doc, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows_i)
        conn.executemany("INSERT INTO shot_terms(shot_id, vocab, term, confidence, source) VALUES(?,?,?,?,?)", rows_t)
        conn.executemany("INSERT INTO shot_fts(rowid, caption, transcript, ocr, tags, place, filename) VALUES(?,?,?,?,?,?,?)", rows_f)
        conn.executemany("INSERT INTO vectors(id, shot_id, asset_id, space, dim, vec, created_at) VALUES(?,?,?,?,?,?,?)", rows_v)
        conn.execute("COMMIT")
        print(f"{sid} shots, {time.time() - t0:.0f} s", flush=True)
    conn.execute("ANALYZE")
    conn.execute("INSERT INTO shot_fts(shot_fts) VALUES('optimize')")
    print(f"built {sid} shots in {time.time() - t0:.0f} s; db {os.path.getsize(s.db_path) / 1e9:.2f} GB", flush=True)


def run(out: Path, models: str, repeats: int = 3, dtype: str = "i8") -> dict:
    os.environ["METACHLORIAN_MODELS"] = models
    s = load_settings(out)
    db = Database(s.db_path)
    eng = SearchEngine(db, s)
    t0 = time.time()
    eng.vectors.dtype = dtype
    eng.vectors.get("visual")
    build_s = time.time() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    n = db.q1("SELECT COUNT(*) n FROM shot_index")["n"]
    hours = db.q1("SELECT SUM(duration) d FROM shot_index")["d"] / 3600
    eng.search(SearchRequest(q="warm up"))
    lat: list[float] = []
    per: dict[str, list[float]] = {}
    for _ in range(repeats):
        for q, f in QUERIES:
            t = time.perf_counter()
            r = eng.search(SearchRequest(q=q, filters=f, limit=40))
            ms = (time.perf_counter() - t) * 1000
            lat.append(ms)
            per.setdefault(q or json.dumps(f), []).append(ms)
            assert r["results"] is not None
    lat.sort()
    res = {"shots": n, "hours": round(hours), "index_build_s": round(build_s, 1), "max_rss_gb": round(rss, 2), "queries": len(lat),
           "median_ms": round(statistics.median(lat), 1), "p95_ms": round(lat[int(0.95 * len(lat)) - 1], 1), "max_ms": round(lat[-1], 1),
           "per_query_median_ms": {k: round(statistics.median(v), 1) for k, v in per.items()},
           "db_gb": round(os.path.getsize(s.db_path) / 1e9, 2), "cpu": os.cpu_count()}
    print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", type=int, default=4_500_000)
    ap.add_argument("--seed-lib")
    ap.add_argument("--models", default=os.environ.get("METACHLORIAN_MODELS", ""))
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    if not a.skip_build:
        build(Path(a.out), a.shots, Path(a.seed_lib))
    r = run(Path(a.out), a.models)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1))
