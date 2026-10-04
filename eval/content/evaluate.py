"""Per-signal accuracy of shot records against the hand-labelled gold set.

Each gold shot is matched to the library shot containing its mid-time in the
same file, so the gold set survives re-segmentation. Scores only fields the
labeller could judge (null = not scored).
usage: python evaluate.py <library_dir> [--gold gold.json] [--json out.json] [--source fused|zs]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from metachlorian.db import Database  # noqa: E402
from metachlorian.records import build_shot_doc  # noqa: E402
from metachlorian.vocab import registry  # noqa: E402

SIZES = ["extreme_close_up", "close_up", "medium_close_up", "medium_shot", "medium_long_shot", "long_shot", "extreme_wide_shot"]
TOD = {"day": "day", "morning": "day", "midday": "day", "afternoon": "day", "golden_hour": "golden", "sunrise": "golden", "sunset": "golden",
       "dawn": "dusk", "dusk": "dusk", "blue_hour": "dusk", "night": "night"}


def bucket(n):
    if n is None:
        return None
    return "0" if n == 0 else "1" if n == 1 else "2-5" if n <= 5 else "6+"


def terms(v):
    if v is None:
        return []
    if isinstance(v, dict):
        v = [v]
    return [x for x in v if isinstance(x, dict) and x.get("term")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("library")
    ap.add_argument("--gold", default=str(Path(__file__).with_name("gold.json")))
    ap.add_argument("--json")
    a = ap.parse_args()
    db = Database(Path(a.library) / "library.sqlite")
    reg = registry()
    setting_v = reg.get("setting")
    gold = json.load(open(a.gold))["shots"]
    m = {k: [0, 0] for k in ("shot_size_exact", "shot_size_within_1", "interior_exterior", "setting_top1", "setting_any", "time_of_day",
                             "people_bucket", "text_present", "blank_flagged")}
    aer = {"tp": 0, "fp": 0, "fn": 0}
    rows = []
    for g in gold:
        a_row = db.q1("SELECT id FROM assets WHERE filename=? AND deleted_at IS NULL", (g["filename"],))
        if not a_row:
            continue
        s = db.q1("SELECT id FROM shots WHERE asset_id=? AND active=1 AND start_s <= ? AND end_s > ?", (a_row["id"], g["mid"], g["mid"]))
        if not s:
            continue
        d = build_shot_doc(db, s["id"])
        f = d["fields"]
        val = lambda n: (f.get(n) or {}).get("value")  # noqa: E731
        row = {"file": g["filename"], "mid": g["mid"]}
        if g.get("blank"):
            roles = [t["term"] for t in terms(val("shot.role"))]
            usable = (val("quality.usable") or {}).get("value")
            ok = "transition" in roles or usable is False
            m["blank_flagged"][0] += ok
            m["blank_flagged"][1] += 1
            rows.append({**row, "blank_flagged": ok})
            continue
        if g["shot_size"]:
            p = (val("camera.shot_size") or {}).get("term")
            row["shot_size"] = (g["shot_size"], p)
            m["shot_size_exact"][1] += 1
            m["shot_size_within_1"][1] += 1
            if p:
                m["shot_size_exact"][0] += p == g["shot_size"]
                m["shot_size_within_1"][0] += abs(SIZES.index(p) - SIZES.index(g["shot_size"])) <= 1
        st = terms(val("content.setting"))
        if g["interior"] is not None:
            ie = [t for t in st if t["term"] in ("interior", "exterior")]
            spec = [t for t in st if t["term"] not in ("interior", "exterior")]
            if ie:
                pred_int = max(ie, key=lambda t: t["confidence"])["term"] == "interior"
            elif spec:
                anc = set(setting_v.ancestors(spec[0]["term"]))
                pred_int = "interior" in anc if anc & {"interior", "exterior"} else None
            else:
                pred_int = None
            m["interior_exterior"][1] += 1
            m["interior_exterior"][0] += pred_int == g["interior"]
            row["interior"] = (g["interior"], pred_int)
        gold_spec = [x for x in g["settings"] if x not in ("interior", "exterior")]
        if gold_spec:
            spec = [t["term"] for t in st if t["term"] not in ("interior", "exterior")]
            # A prediction is right if it is a gold term, a broader term of one, or narrower than one.
            ok_terms = set(gold_spec) | {x for t in gold_spec for x in setting_v.ancestors(t)} | {x for t in gold_spec for x in setting_v.narrower(t)}
            m["setting_top1"][1] += 1
            m["setting_any"][1] += 1
            m["setting_top1"][0] += bool(spec) and spec[0] in ok_terms
            m["setting_any"][0] += any(t in ok_terms for t in spec)
            row["setting"] = (gold_spec, spec[:3])
        if g["time_of_day"]:
            p = (val("content.time_of_day") or {}).get("term")
            m["time_of_day"][1] += 1
            m["time_of_day"][0] += TOD.get(p) == TOD[g["time_of_day"]]
            row["time_of_day"] = (g["time_of_day"], p)
        if g["people"] is not None:
            pc = val("people.count")
            p = bucket(pc.get("value") if isinstance(pc, dict) else pc)
            m["people_bucket"][1] += 1
            m["people_bucket"][0] += p == g["people"]
            row["people"] = (g["people"], p)
        if g["aerial"] is not None:
            p = any(t["term"] == "aerial" and t["confidence"] >= 0.45 for t in terms(val("camera.movement")))
            aer["tp"] += p and g["aerial"]
            aer["fp"] += p and not g["aerial"]
            aer["fn"] += (not p) and g["aerial"]
            row["aerial"] = (g["aerial"], p)
        has_text = bool((val("content.ocr_text") or ""))
        m["text_present"][1] += 1
        m["text_present"][0] += has_text == g["text"]
        rows.append(row)
    P = aer["tp"] / max(1, aer["tp"] + aer["fp"])
    R = aer["tp"] / max(1, aer["tp"] + aer["fn"])
    res = {k: {"accuracy": round(v[0] / v[1], 3) if v[1] else None, "n": v[1]} for k, v in m.items()}
    res["aerial"] = {"precision": round(P, 3), "recall": round(R, 3), "f1": round(2 * P * R / max(1e-9, P + R), 3), **aer}
    out = {"shots_scored": len(rows), "metrics": res}
    print(json.dumps(out, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps({**out, "rows": rows}, indent=1, default=str))


if __name__ == "__main__":
    main()
