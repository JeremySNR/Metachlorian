"""CI quality gates that need no external footage; exit 1 when a metric drops below its floor.

1. Shot boundaries: synthetic gold sequences built from generated sources (lavfi test patterns with motion, and
   procedural textured stills filmed by a moving virtual camera with a moving subject), joined with exactly known
   hard cuts, dissolves, fades through black/white and wipes (composed as in sbd/make_gold.py), plus single-frame
   flash decoys that must NOT be detected. Same detector call and one-to-one matching as sbd/evaluate.py.
2. Camera motion: motion/make_gold.py's virtual camera over 4 procedural stills x 10 moves, scored with the rule
   in motion/evaluate.py.
3. Parser: the four spec queries parse as specified (test_parser_spec_queries).

Everything is seeded and encoded single-threaded, so a run is byte-for-byte reproducible.

usage: python ci_gates.py [--json out.json] [--keep DIR] [--workers N]
"""
import argparse, importlib.util, json, math, os, random, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL.parent / "core"))
from metachlorian.media import ffmpeg  # noqa: E402
from metachlorian.media import motion as M  # noqa: E402


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, EVAL / rel)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


SBD = _load("sbd_evaluate", "sbd/evaluate.py")      # match(), run("ours", ...)
MG = _load("motion_make_gold", "motion/make_gold.py")  # render(), MOVES, LABELS, FPS, W, H

FLOORS = {"sbd_f1": 0.85, "motion_correct": 36, "parser_spec": 4}  # docs/roadmap.md, item 1 step 8
FPS, SW, SH = 30, 480, 270
N_SEQ, SEED = 8, 7


def still(seed, w, h):
    """A richly textured 'photo': multi-octave colour noise, a light gradient and a few hundred shapes."""
    r = np.random.default_rng(seed)
    img = np.full((h, w, 3), r.uniform(50, 200, 3), np.float32)
    for cells, amp in ((4, 70), (16, 45), (64, 25), (256, 14)):
        g = r.normal(0, 1, (max(2, cells * h // w), cells, 3)).astype(np.float32)
        img += cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC) * amp
    img += (np.linspace(-0.5, 0.5, h, dtype=np.float32)[:, None, None]) * r.uniform(-90, 90, 3).astype(np.float32)
    img = np.clip(img, 0, 255).astype(np.uint8)
    s = w / 1000
    for _ in range(int(r.integers(250, 400))):
        col = tuple(int(c) for c in r.integers(0, 256, 3)); x, y = int(r.integers(w)), int(r.integers(h))
        k = r.integers(4); sz = int(r.uniform(4, 60) * s)
        if k == 0:
            cv2.circle(img, (x, y), sz, col, -1 if r.random() < 0.6 else max(1, int(2 * s)), cv2.LINE_AA)
        elif k == 1:
            cv2.rectangle(img, (x, y), (x + sz, y + int(r.uniform(0.3, 2) * sz)), col, -1)
        elif k == 2:
            cv2.line(img, (x, y), (x + int(r.normal(0, 80 * s)), y + int(r.normal(0, 80 * s))), col, max(1, int(r.uniform(1, 5) * s)), cv2.LINE_AA)
        else:
            pts = (np.array([x, y]) + r.normal(0, sz, (int(r.integers(3, 7)), 2))).astype(np.int32)
            cv2.fillPoly(img, [pts], col, cv2.LINE_AA)
    return cv2.GaussianBlur(img, (0, 0), 0.7 * s)


# ---------------------------------------------------------------- shot boundaries

def clip_pool():
    """Source 'clips': each segment is cut from one of these at a random time offset (fixed seed)."""
    r = np.random.default_rng(SEED)
    S = f"s={SW}x{SH}:r={FPS}"
    up = f"scale={SW}:{SH}:flags=neighbor"
    hexc = lambda: "#%02x%02x%02x" % tuple(int(c) for c in r.integers(0, 256, 3))  # noqa: E731
    lav = [
        f"testsrc2={S},hue=h={r.integers(360)}",
        f"testsrc2={S},hue=h={r.integers(360)}:s=0.6,hflip",
        f"cellauto=s=160x90:r={FPS}:rule=110:random_seed=3:random_fill_ratio=0.5,{up},colorchannelmixer=rr=0.9:gg=0.6:bb=0.2",
        f"cellauto=s=240x135:r={FPS}:rule=30:random_seed=5,{up},negate,colorchannelmixer=rr=0.3:gg=0.7:bb=0.9",
        f"life=s=160x90:r={FPS}:seed=3:ratio=0.3:mold=8:life_color={hexc()}:death_color={hexc()}:mold_color={hexc()},{up}",
        f"gradients={S}:seed=4:speed=0.03:nb_colors=5:type=radial:" + ":".join(f"c{i}={hexc()}" for i in range(5)),  # unset colours are random
        f"gradients={S}:seed=9:speed=0.02:nb_colors=3:type=spiral:" + ":".join(f"c{i}={hexc()}" for i in range(3)),
        f"smptebars={S},scroll=h=0.004",
        f"rgbtestsrc={S},scroll=v=0.003,hue=h={r.integers(360)}",
    ]
    clips = [("lavfi", s) for s in lav]
    # Procedural stills (and two Mandelbrot frames) under a virtual camera, half with a moving subject. A lavfi
    # mandelbrot *zoom* is not used as video: new fractal structure keeps emerging out of the colour field, which no
    # camera produces and which the dissolve test reads as a blend (11 of 19 false positives in a trial run, F1 0.894),
    # and deep zooms render too slowly for CI (430 s for 20 s of video).
    stills = [100 + i for i in range(8)] + ["mandelbrot=s=1280x720:start_scale=1.2", "mandelbrot=s=1280x720:start_x=-0.7436:start_y=0.1318:start_scale=0.01"]
    for i, st in enumerate(stills):
        clips.append(("camera", dict(still=st, vx=r.uniform(-0.06, 0.06), vy=r.uniform(-0.03, 0.03), vz=r.choice([0, r.uniform(-0.05, 0.05)]),
                                     shake=r.choice([0.0, 0.002, 0.005]), subject=bool(i % 2))))
    return clips


def lavfi_frames(spec, start, n, size=(SW, SH), grain=None):
    out = subprocess.run([ffmpeg.ffmpeg_bin(), "-v", "error", "-f", "lavfi", "-i", spec, "-ss", f"{start:.3f}", "-frames:v", str(n),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(out, np.uint8).reshape(-1, size[1], size[0], 3)
    if grain is not None:  # sensor noise in numpy: ffmpeg's noise filter is not reproducible after some sources
        return [np.clip(fr[min(i, len(fr) - 1)] + 3.0 * grain.standard_normal(fr.shape[1:], np.float32), 0, 255).astype(np.uint8) for i in range(n)]
    return [fr[min(i, len(fr) - 1)].copy() for i in range(n)]


def camera_frames(img, c, start, n, r):
    h0, w0 = img.shape[:2]; base_w = w0 * 0.5
    shake = np.cumsum(r.normal(0, 1, (n, 2)), 0) * 0.3 + r.normal(0, 1, (n, 2))
    shake = shake * c["shake"] * w0
    sub = dict(p=r.uniform([0, 0], [SW, SH]), v=r.uniform(-60, 60, 2), ax=(int(r.integers(15, 45)), int(r.integers(25, 70))),
               col=tuple(int(x) for x in r.integers(0, 256, 3)))
    frames = []
    for i in range(n):
        t = start + i / FPS - 5.0
        ww = base_w / math.exp(c["vz"] * t); hh = ww * SH / SW
        x = w0 / 2 + c["vx"] * base_w * t + shake[i, 0]; y = h0 / 2 + c["vy"] * base_w * t + shake[i, 1]
        A = np.array([[SW / ww, 0, -(x - ww / 2) * SW / ww], [0, SH / hh, -(y - hh / 2) * SH / hh]], np.float32)
        f = cv2.warpAffine(img, A, (SW, SH), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REFLECT)
        if c["subject"]:
            p = sub["p"] + sub["v"] * i / FPS
            cv2.ellipse(f, (int(p[0]) % SW, int(p[1]) % SH), sub["ax"], 10 * i / FPS, 0, 360, sub["col"], -1, cv2.LINE_AA)
        frames.append(np.clip(f + 2.0 * r.standard_normal(f.shape, np.float32), 0, 255).astype(np.uint8))
    return frames


def build_sequence(si, out):
    """One gold sequence with transitions composed as in sbd/make_gold.py; frames stream to the encoder.

    Differences: more gradual transitions and flash decoys (to measure them), and decoys are recorded where the
    frame actually lands (make_gold.py records segment start + j, off by L for dissolves/wipes and by the hold
    for fades) and kept out of the transition ramps.
    """
    rng = random.Random(SEED * 1000 + si); r = np.random.default_rng(SEED * 1000 + si)
    clips = clip_pool(); stills = {}
    enc = subprocess.Popen([ffmpeg.ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SW}x{SH}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "1", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    buf, written, truth, decoys, segs, prev = [], 0, [], [], [], None
    for k in range(rng.randint(9, 14)):
        ci = rng.choice([i for i in range(len(clips)) if i != prev]); prev = ci
        n = int(rng.uniform(1.2, 7.0) * FPS); start = rng.uniform(2, 10)  # skip life's start-up die-off
        kind_src, c = clips[ci]
        if kind_src == "lavfi":
            seg = lavfi_frames(c, start, n, grain=r)
        else:
            img = stills.get(c["still"])
            if img is None:
                img = stills[c["still"]] = lavfi_frames(c["still"], 0, 1, (1280, 720))[0] if isinstance(c["still"], str) else still(c["still"], 1280, 720)
            seg = camera_frames(img, c, start, n, r)
        total = written + len(buf)
        if k == 0:
            kind, L = "first", 0
        else:
            x = rng.random()
            kind = "cut" if x < 0.5 else "dissolve" if x < 0.75 else "fade_black" if x < 0.85 else "fade_white" if x < 0.95 else "wipe"
            L = 0 if kind == "cut" else min(rng.randint(10, 30), len(seg) - 2, len(buf) - 2) if kind in ("dissolve", "wipe") else rng.randint(8, 20)
        # Flash decoy inside ~30% of segments, outside the transition ramps (+160 on one frame, like make_gold.py).
        flash = rng.randint(L + 5, len(seg) - 6) if len(seg) - 6 > L + 5 and rng.random() < 0.3 else None
        if flash is not None:
            seg[flash] = np.clip(seg[flash].astype(np.int16) + 160, 0, 255).astype(np.uint8)
        if kind in ("first", "cut"):
            if kind == "cut":
                truth.append({"type": "cut", "frame": total, "span": [total, total]})
            seg_at = total; buf.extend(seg)
        elif kind in ("dissolve", "wipe"):
            a0 = len(buf) - L
            for i in range(L):
                al = (i + 1) / (L + 1); A = buf[a0 + i].astype(np.float32); B = seg[i].astype(np.float32)
                if kind == "dissolve":
                    buf[a0 + i] = (A * (1 - al) + B * al).astype(np.uint8)
                else:
                    A[:, :int(SW * al)] = B[:, :int(SW * al)]; buf[a0 + i] = A.astype(np.uint8)
            truth.append({"type": kind, "frame": total - L + L // 2, "span": [total - L, total]})
            seg_at = total - L; buf.extend(seg[L:])
        else:
            hold = rng.randint(0, 12); col = 0 if kind == "fade_black" else 255; a0 = len(buf) - L
            for i in range(L):
                al = (i + 1) / (L + 1)
                buf[a0 + i] = (buf[a0 + i].astype(np.float32) * (1 - al) + col * al).astype(np.uint8)
                seg[i] = (seg[i].astype(np.float32) * al + col * (1 - al)).astype(np.uint8)
            buf.extend([np.full((SH, SW, 3), col, np.uint8)] * hold)
            truth.append({"type": kind, "frame": total - L + L + hold // 2, "span": [total - L, total + L + hold]})
            seg_at = total + hold; buf.extend(seg)
        if flash is not None:
            decoys.append(seg_at + flash)
        segs.append([seg_at, ci])
        while len(buf) > 40:  # transitions only reach back <= 30 frames
            enc.stdin.write(buf.pop(0).tobytes()); written += 1
    for fr in buf:
        enc.stdin.write(fr.tobytes()); written += 1
    enc.stdin.close(); enc.wait()
    return {"video": out.name, "fps": FPS, "frames": written, "transitions": truth, "flash_decoys": decoys, "segments": segs}


def sbd_one(args):
    si, tmp = args
    out = Path(tmp) / f"sbd_{si:02d}.mp4"
    gt = build_sequence(si, out)
    json.dump(gt, open(out.with_suffix(".json"), "w"), indent=1)
    pred = SBD.run("ours", str(out), gt["fps"])
    tp, fp, fn, bt = SBD.match(pred, gt["transitions"])
    flash_fp = sum(1 for p in pred if any(abs(p - d) <= 1 for d in gt["flash_decoys"]))
    return tp, fp, fn, bt, flash_fp, len(gt["flash_decoys"]), gt["frames"]


def gate_sbd(tmp, pool):
    TP = FP = FN = flash_fp = n_flash = frames = 0; types = {}
    for tp, fp, fn, bt, ffp, nf, nfr in pool.map(sbd_one, [(i, tmp) for i in range(N_SEQ)]):
        TP += tp; FP += fp; FN += fn; flash_fp += ffp; n_flash += nf; frames += nfr
        for k, (ok, n) in bt.items():
            types.setdefault(k, [0, 0]); types[k][0] += ok; types[k][1] += n
    P = TP / max(1, TP + FP); R = TP / max(1, TP + FN); F = 2 * P * R / max(1e-9, P + R)
    return {"f1": round(F, 3), "precision": round(P, 3), "recall": round(R, 3), "tp": TP, "fp": FP, "fn": FN, "sequences": N_SEQ, "frames": frames,
            "flash_false_positives": f"{flash_fp}/{n_flash}", "recall_by_type": {k: f"{v[0]}/{v[1]}" for k, v in sorted(types.items())}}


# ---------------------------------------------------------------- camera motion

PRIMARY = {"static", "pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_in", "zoom_out", "push_in", "pull_out", "truck_left", "truck_right"}


def motion_correct(labels, pred):
    """The rule in motion/evaluate.py."""
    hit = all(lbl in pred for lbl in labels)
    if not hit and labels in (["zoom_in"], ["zoom_out"]):
        hit = {"zoom_in": "push_in", "zoom_out": "pull_out"}[labels[0]] in pred
    return hit and not ((set(pred) & PRIMARY) - set(labels) - {"push_in", "pull_out"})


def motion_one(args):
    si, tmp = args
    img = still(500 + si, 3840, 2160)  # like a 4K frame grab
    rng = np.random.default_rng(3 + si); rows = []
    for name, spec in MG.MOVES.items():
        fn = Path(tmp) / f"motion_{si}_{name.replace('+', '_')}.mp4"
        p = subprocess.Popen([ffmpeg.ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{MG.W}x{MG.H}", "-r", str(MG.FPS),
                              "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "1", "-pix_fmt", "yuv420p", str(fn)], stdin=subprocess.PIPE)
        for f in MG.render(img, spec, rng):
            p.stdin.write(f.tobytes())
        p.stdin.close(); p.wait()
        r = M.analyse_shot(fn, 0.0, MG.DUR)
        pred = {m["term"]: m["confidence"] for m in r["movements"] if m["confidence"] >= 0.4}
        rows.append({"file": fn.name, "gold": MG.LABELS[name], "pred": pred, "correct": motion_correct(MG.LABELS[name], pred),
                     "stats": {k: r.get("stats", {}).get(k) for k in ("vx", "vy", "zoom", "jitter", "parallax_px")}})
    return rows


def gate_motion(tmp, pool):
    rows = [x for rs in pool.map(motion_one, [(i, tmp) for i in range(4)]) for x in rs]
    per = {}
    for x in rows:
        d = per.setdefault("+".join(x["gold"]), [0, 0]); d[0] += x["correct"]; d[1] += 1
    return {"correct": sum(x["correct"] for x in rows), "clips": len(rows), "per_class": {k: f"{a}/{b}" for k, (a, b) in sorted(per.items())},
            "misses": [{k: x[k] for k in ("file", "gold", "pred", "stats")} for x in rows if not x["correct"]]}


# ---------------------------------------------------------------- parser

def gate_parser():
    from metachlorian.search.parse import parse
    checks = {
        "Find slow, wide drone shots of a coastline at golden hour, no people, at least 8 seconds, 4K.": lambda p: (
            p.filters == {"min_duration": 8.0, "min_height": 2160, "max_people": 0} and p.prefer["camera_movement"] == ["aerial"]
            and "coast" in p.prefer["setting"] and p.prefer["time_of_day"] == ["golden_hour"]
            and "long_shot" in p.prefer["shot_size"] and p.prefer["pace"] == ["slow"]),
        "What do we have from Lisbon that we are actually cleared to use on paid social?": lambda p: (
            p.rights == {"channel": "paid_social"} and p.place == ["Lisbon"]),
        "Give me three B-roll cutaways that would work under this interview line about family holidays.": lambda p: (
            p.limit == 3 and p.semantic == "family holidays" and "interview" not in p.prefer.get("shot_role", [])),
        "handheld street food close-ups, busy, night": lambda p: (
            p.prefer["camera_movement"] == ["handheld"] and p.prefer["time_of_day"] == ["night"] and p.prefer["shot_size"] == ["close_up"]),
    }
    failed = []
    for q, ok in checks.items():
        try:
            good = bool(ok(parse(q)))
        except Exception as e:  # a missing key is a failed parse
            good = False; q = f"{q} ({type(e).__name__}: {e})"
        if not good:
            failed.append(q)
    return {"passed": len(checks) - len(failed), "queries": len(checks), "failed": failed}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json"); ap.add_argument("--keep", help="keep the generated clips in this directory")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    a = ap.parse_args()
    t0 = time.time()
    tmp = a.keep or tempfile.mkdtemp(prefix="mc-ci-gates-"); Path(tmp).mkdir(parents=True, exist_ok=True)
    try:
        with ProcessPoolExecutor(a.workers) as pool:
            t = time.time(); sbd = gate_sbd(tmp, pool); sbd["seconds"] = round(time.time() - t, 1)
            t = time.time(); mot = gate_motion(tmp, pool); mot["seconds"] = round(time.time() - t, 1)
        par = gate_parser()
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    values = {"sbd_f1": sbd["f1"], "motion_correct": mot["correct"], "parser_spec": par["passed"]}
    gates = {k: {"value": v, "floor": FLOORS[k], "pass": v >= FLOORS[k]} for k, v in values.items()}
    summary = {"gates": gates, "sbd": sbd, "motion": mot, "parser": par, "seconds": round(time.time() - t0, 1)}
    print(json.dumps(summary))
    if a.json:
        json.dump(summary, open(a.json, "w"), indent=1)
    for k, g in gates.items():
        print(f"{'PASS' if g['pass'] else 'FAIL'} {k}: {g['value']} (floor {g['floor']})", file=sys.stderr)
    failed = [k for k, g in gates.items() if not g["pass"]]
    if failed:
        print("CI gates failed: " + ", ".join(f"{k} {gates[k]['value']} < {gates[k]['floor']}" for k in failed), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
