"""Build shot-boundary gold sequences from real footage with exact, known transitions.

Segments are cut from CC-BY source clips (see eval/media/SOURCES.md), joined
with hard cuts, dissolves, fades through black/white and wipes, and camera
flash decoys are inserted inside some shots (they must NOT be detected).
Ground truth is written as JSON in frame units at 30 fps.

usage: python make_gold.py <media_dir> <out_dir> [n_sequences] [seed]
"""
import json, random, subprocess, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from metachlorian.media import ffmpeg  # noqa: E402

FPS, W, H = 30, 640, 360


def probe_dur(p):
    return float(ffmpeg.ffprobe(p)["format"]["duration"])


def read_segment(path, start, n):
    frames = []
    for fr in ffmpeg.iter_frames(path, W, H, fps=FPS, start=start, duration=n / FPS + 0.5):
        frames.append(fr)
        if len(frames) == n:
            break
    while len(frames) < n:
        frames.append(frames[-1])
    return frames


def main():
    media, out = Path(sys.argv[1]), Path(sys.argv[2])
    nseq = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    rng = random.Random(int(sys.argv[4]) if len(sys.argv) > 4 else 7)
    out.mkdir(parents=True, exist_ok=True)
    clips = [p for p in sorted(media.rglob("*")) if p.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm") and probe_dur(p) > 6]
    print(f"{len(clips)} source clips")
    for si in range(nseq):
        frames_out, truth, decoys = [], [], []
        prev_clip = None
        nseg = rng.randint(9, 14)
        for k in range(nseg):
            clip = rng.choice([c for c in clips if c != prev_clip])
            prev_clip = clip
            dur = probe_dur(clip)
            seg_s = rng.uniform(1.2, 7.0)
            start = rng.uniform(0, max(0.0, dur - seg_s - 0.5))
            seg = read_segment(clip, start, int(seg_s * FPS))
            # Flash decoy inside ~15% of segments.
            if len(seg) > 20 and rng.random() < 0.15:
                j = rng.randint(5, len(seg) - 5)
                seg[j] = np.clip(seg[j].astype(np.int16) + 160, 0, 255).astype(np.uint8)
                decoys.append(len(frames_out) + j)
            if not frames_out:
                frames_out.extend(seg)
                continue
            r = rng.random()
            kind = "cut" if r < 0.6 else "dissolve" if r < 0.8 else "fade_black" if r < 0.9 else "fade_white" if r < 0.95 else "wipe"
            if kind == "cut":
                truth.append({"type": "cut", "frame": len(frames_out), "span": [len(frames_out), len(frames_out)]})
                frames_out.extend(seg)
            elif kind in ("dissolve", "wipe"):
                L = rng.randint(10, 30)
                L = min(L, len(seg) - 2, len(frames_out) - 2)
                a0 = len(frames_out) - L
                for i in range(L):
                    al = (i + 1) / (L + 1)
                    A = frames_out[a0 + i].astype(np.float32)
                    B = seg[i].astype(np.float32)
                    if kind == "dissolve":
                        frames_out[a0 + i] = (A * (1 - al) + B * al).astype(np.uint8)
                    else:
                        x = int(W * al)
                        m = A.copy(); m[:, :x] = B[:, :x]
                        frames_out[a0 + i] = m.astype(np.uint8)
                frames_out.extend(seg[L:])
                truth.append({"type": kind, "frame": a0 + L // 2, "span": [a0, a0 + L]})
            else:
                L = rng.randint(8, 20); hold = rng.randint(0, 12)
                col = 0 if kind == "fade_black" else 255
                a0 = len(frames_out) - L
                for i in range(L):
                    al = (i + 1) / (L + 1)
                    frames_out[a0 + i] = (frames_out[a0 + i].astype(np.float32) * (1 - al) + col * al).astype(np.uint8)
                frames_out.extend([np.full((H, W, 3), col, np.uint8)] * hold)
                for i in range(L):
                    al = (i + 1) / (L + 1)
                    seg[i] = (seg[i].astype(np.float32) * al + col * (1 - al)).astype(np.uint8)
                mid = a0 + L + hold // 2
                truth.append({"type": kind, "frame": mid, "span": [a0, a0 + 2 * L + hold]})
                frames_out.extend(seg)
        name = f"sbd_{si:02d}.mp4"
        p = subprocess.Popen([ffmpeg.ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                              "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(out / name)], stdin=subprocess.PIPE)
        for fr in frames_out:
            p.stdin.write(fr.tobytes())
        p.stdin.close(); p.wait()
        json.dump({"video": name, "fps": FPS, "frames": len(frames_out), "transitions": truth, "flash_decoys": decoys},
                  open(out / f"sbd_{si:02d}.json", "w"), indent=1)
        print(name, len(frames_out), [t["type"] for t in truth])


if __name__ == "__main__":
    main()
