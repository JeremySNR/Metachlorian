"""Known-item search for words people remember hearing or reading: query with a
phrase from a shot's transcript or on-screen text and check where that shot ranks.
Objective (no judge), complementing the pooled visual-description judgments.

Phrases are drawn deterministically from the library's own transcripts and OCR,
so the test checks retrieval, not recognition accuracy.

usage: python known_item.py <library> [--json out.json]
"""
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from metachlorian.config import load_settings  # noqa: E402
from metachlorian.db import Database  # noqa: E402
from metachlorian.search import engine as E  # noqa: E402
import relevance as R  # noqa: E402

STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "it", "i", "you", "that", "this", "we", "be", "for", "at", "with"}


def phrases(db: Database, kind: str, n: int, rng: random.Random) -> list[tuple[str, int]]:
    name = "audio.transcript" if kind == "speech" else "content.ocr_text"
    rows = db.q("SELECT target_id, value FROM signals WHERE level='shot' AND name=? ORDER BY target_id", (name,))
    out = []
    for r in rows:
        text = json.loads(r["value"]) if r["value"].startswith('"') else r["value"]
        words = [w for w in re.findall(r"[\w']+", str(text)) if len(w) > 1]
        if len(words) < 4:
            continue
        i = rng.randrange(0, len(words) - 3)
        span = words[i:i + 4]
        if sum(w.lower() not in STOP for w in span) < 2:
            continue
        out.append((" ".join(span), r["target_id"]))
    rng.shuffle(out)
    return out[:n]


def main():
    lib = Path(sys.argv[1])
    s = load_settings(lib)
    db = Database(s.db_path)
    eng = E.SearchEngine(db, s)
    rng = random.Random(7)
    items = [("speech", p, sid) for p, sid in phrases(db, "speech", 20, rng)] + [("text", p, sid) for p, sid in phrases(db, "ocr", 20, rng)]
    res: dict[str, dict] = {}
    for v in ("hybrid", "visual_only", "keyword_only"):
        rr, hit = {"speech": [], "text": []}, {"speech": [], "text": []}
        for kind, q, sid in items:
            ranked = R.run_variant(eng, q, v)
            rank = ranked.index(sid) + 1 if sid in ranked else None
            rr[kind].append(1 / rank if rank else 0.0)
            hit[kind].append(1 if rank else 0)
        res[v] = {k: {"mrr@10": round(sum(rr[k]) / max(1, len(rr[k])), 3), "hit@10": round(sum(hit[k]) / max(1, len(hit[k])), 3),
                      "n": len(rr[k])} for k in rr}
    print(json.dumps(res, indent=1))
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps({"items": items, "results": res}, indent=1))


if __name__ == "__main__":
    main()
