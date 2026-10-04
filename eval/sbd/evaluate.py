"""Score shot boundary detectors against the gold sequences.

Matching is one-to-one: a predicted boundary matches a true transition when it
falls inside the transition span widened by 2 frames (hard cuts: +-2 frames).
usage: python evaluate.py <gold_dir> [--detectors ours,adaptive,content,histogram] [--json out.json]
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from metachlorian.media import shots as S  # noqa: E402

TOL = 2


def match(pred_frames, truth):
    used = set(); tp = 0; by_type = {}
    for t in truth:
        lo, hi = t["span"][0] - TOL, t["span"][1] + TOL
        cands = [i for i, p in enumerate(pred_frames) if i not in used and lo <= p <= hi]
        ok = bool(cands)
        if ok:
            best = min(cands, key=lambda i: abs(pred_frames[i] - t["frame"])); used.add(best); tp += 1
        d = by_type.setdefault(t["type"], [0, 0]); d[0] += ok; d[1] += 1
    return tp, len(pred_frames) - len(used), len(truth) - tp, by_type


def run(det, video, fps):
    if det == "ours":
        shots, f = S.segment(video, fps)
        return [round(s * fps) for s in S.boundaries_seconds(shots)]
    return [round(s * fps) for s in S.pyscenedetect(video, det)]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("gold"); ap.add_argument("--detectors", default="ours,adaptive,content,histogram"); ap.add_argument("--json")
    a = ap.parse_args()
    gold = sorted(Path(a.gold).glob("*.json"))
    results = {}
    for det in a.detectors.split(","):
        TP = FP = FN = 0; types = {}; t0 = time.time(); frames = 0; flash_fp = 0
        for g in gold:
            gt = json.load(open(g)); frames += gt["frames"]
            pred = run(det, str(g.with_suffix(".mp4")), gt["fps"])
            tp, fp, fn, bt = match(pred, gt["transitions"])
            flash_fp += sum(1 for p in pred if any(abs(p - d) <= 1 for d in gt["flash_decoys"]))
            TP += tp; FP += fp; FN += fn
            for k, (ok, n) in bt.items():
                types.setdefault(k, [0, 0]); types[k][0] += ok; types[k][1] += n
        el = time.time() - t0
        P = TP / max(1, TP + FP); R = TP / max(1, TP + FN); F = 2 * P * R / max(1e-9, P + R)
        results[det] = {"precision": round(P, 3), "recall": round(R, 3), "f1": round(F, 3), "tp": TP, "fp": FP, "fn": FN,
                        "flash_false_positives": flash_fp, "recall_by_type": {k: f"{v[0]}/{v[1]}" for k, v in sorted(types.items())},
                        "fps_processed": round(frames / el, 1)}
        print(det, json.dumps(results[det]))
    if a.json:
        json.dump(results, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
