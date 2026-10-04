"""Sample shots for hand labelling and render labelled contact sheets.

Picks up to N shots per file (longest first, then spread), skipping shots
under 1 s, and writes composites of 4 shots (each shot = 4 keyframes in a 2x2
grid with its id) so a labeller can review many shots per image. Shots are
identified by (filename, mid-time), which survives re-segmentation.
usage: python sample.py <library_dir> <out_dir> [per_file]
"""
import json
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np


def main():
    lib, out = Path(sys.argv[1]), Path(sys.argv[2])
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(lib / "library.sqlite"))
    db.row_factory = sqlite3.Row
    picks = []
    for a in db.execute("SELECT id, uid, filename FROM assets WHERE deleted_at IS NULL ORDER BY filename"):
        shots = [dict(s) for s in db.execute("SELECT idx, start_s, end_s, keyframes FROM shots WHERE asset_id=? AND active=1 AND end_s-start_s >= 1.0 ORDER BY idx", (a["id"],))]
        if not shots:
            continue
        chosen = [max(shots, key=lambda s: s["end_s"] - s["start_s"])]
        if per > 1 and len(shots) > 1:
            rest = [s for s in shots if s is not chosen[0]]
            step = max(1, len(rest) // (per - 1))
            chosen += rest[::step][: per - 1]
        for s in chosen:
            picks.append({"filename": a["filename"], "asset_uid": a["uid"], "idx": s["idx"], "start": round(s["start_s"], 2), "end": round(s["end_s"], 2),
                          "mid": round((s["start_s"] + s["end_s"]) / 2, 2), "keyframes": json.loads(s["keyframes"])})
    tiles = []
    for i, p in enumerate(picks):
        imgs = []
        for kf in (p["keyframes"] or [])[:4]:
            im = cv2.imread(str(lib / "media" / p["asset_uid"] / kf["file"]))
            if im is not None:
                imgs.append(cv2.resize(im, (384, 216)))
        while len(imgs) < 4:
            imgs.append(imgs[-1] if imgs else np.zeros((216, 384, 3), np.uint8))
        grid = np.vstack([np.hstack(imgs[:2]), np.hstack(imgs[2:4])])
        cv2.rectangle(grid, (0, 0), (360, 30), (0, 0, 0), -1)
        cv2.putText(grid, f"#{i} {p['filename'][:28]} {p['end'] - p['start']:.1f}s", (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        tiles.append(grid)
    for b in range(0, len(tiles), 4):
        group = tiles[b:b + 4]
        while len(group) < 4:
            group.append(np.zeros_like(tiles[0]))
        comp = np.vstack([np.hstack(group[:2]), np.hstack(group[2:])])
        cv2.imwrite(str(out / f"sheet_{b // 4:03d}.jpg"), cv2.resize(comp, (1536, 864)), [cv2.IMWRITE_JPEG_QUALITY, 80])
    for p in picks:
        p.pop("keyframes")
    (out / "picks.json").write_text(json.dumps(picks, indent=1))
    print(len(picks), "shots,", (len(tiles) + 3) // 4, "sheets")


if __name__ == "__main__":
    main()
