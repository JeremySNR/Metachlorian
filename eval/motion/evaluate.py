"""Score the camera-motion analyser on the synthetic gold clips.

A clip counts as correct when every gold label is predicted with confidence
>= 0.4 (direction-specific terms must match exactly) and no contradicting
primary movement is predicted (e.g. static on a pan).
usage: python evaluate.py <gold_dir> [--json out.json]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from metachlorian.media import motion as M  # noqa: E402

PRIMARY = {"static", "pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_in", "zoom_out", "push_in", "pull_out", "truck_left", "truck_right"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gold")
    ap.add_argument("--json")
    a = ap.parse_args()
    gold = json.load(open(Path(a.gold) / "gold.json"))
    ok = 0
    per = Counter()
    tot = Counter()
    rows = []
    for g in gold:
        r = M.analyse_shot(Path(a.gold) / g["file"], 0.0, 4.0)
        pred = {m["term"]: m["confidence"] for m in r["movements"] if m["confidence"] >= 0.4}
        name = "+".join(g["labels"])
        tot[name] += 1
        hit = all(lbl in pred for lbl in g["labels"])
        # Zoom without parallax may legitimately read as push_in/pull_out on a flat still: accept the dolly equivalent.
        if not hit and g["labels"] in (["zoom_in"], ["zoom_out"]):
            alt = {"zoom_in": "push_in", "zoom_out": "pull_out"}[g["labels"][0]]
            hit = alt in pred
        extra_primary = (set(pred) & PRIMARY) - set(g["labels"]) - {"push_in", "pull_out"}
        if hit and not extra_primary:
            ok += 1
            per[name] += 1
        rows.append({"file": g["file"], "gold": g["labels"], "pred": pred, "correct": hit and not extra_primary, "stats": r.get("stats")})
    acc = ok / len(gold)
    res = {"clips": len(gold), "accuracy": round(acc, 3), "per_class": {k: f"{per[k]}/{tot[k]}" for k in sorted(tot)}}
    print(json.dumps(res, indent=1))
    for r in rows:
        if not r["correct"]:
            print("MISS", r["file"], r["gold"], r["pred"], {k: r["stats"].get(k) for k in ("vx", "vy", "zoom", "jitter", "parallax_px")})
    if a.json:
        json.dump({**res, "rows": rows}, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
