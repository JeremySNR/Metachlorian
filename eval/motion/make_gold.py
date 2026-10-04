"""Camera-motion gold clips with exact ground truth.

Each clip is rendered from a single real high-resolution still (taken from CC-BY
4K footage) by moving a virtual camera window over it: pans, tilts, zooms,
handheld shake (band-limited random walk), static (sensor noise only) and
combinations. Ground truth labels use the camera_movement vocabulary.

usage: python make_gold.py <out_dir> <still1.png> [<still2.png> ...]
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

FPS, W, H, DUR = 25, 960, 540, 4.0
MOVES = {
    "static": dict(),
    "pan_left": dict(vx=-0.12), "pan_right": dict(vx=0.12),
    "tilt_up": dict(vy=-0.10), "tilt_down": dict(vy=0.10),
    "zoom_in": dict(vz=0.12), "zoom_out": dict(vz=-0.12),
    "handheld": dict(shake=0.012),
    "handheld+pan_right": dict(vx=0.10, shake=0.012),
    "slow_pan_left": dict(vx=-0.05),
}
LABELS = {"static": ["static"], "pan_left": ["pan_left"], "pan_right": ["pan_right"], "tilt_up": ["tilt_up"], "tilt_down": ["tilt_down"],
          "zoom_in": ["zoom_in"], "zoom_out": ["zoom_out"], "handheld": ["handheld"], "handheld+pan_right": ["handheld", "pan_right"],
          "slow_pan_left": ["pan_left"]}


def render(img: np.ndarray, spec: dict, rng: np.random.Generator) -> list[np.ndarray]:
    h0, w0 = img.shape[:2]
    n = int(FPS * DUR)
    # Window covers 55% of the still's width, centred, with room to move.
    base_w = w0 * 0.55
    cx, cy = w0 / 2, h0 / 2
    shake = np.zeros((n, 2))
    if spec.get("shake"):
        walk = rng.normal(0, 1, (n, 2))
        k = np.ones(3) / 3  # keep 2-8 Hz energy
        walk = np.stack([np.convolve(walk[:, i], k, mode="same") for i in range(2)], 1)
        shake = walk * spec["shake"] * w0
    frames = []
    for i in range(n):
        t = i / FPS
        z = math.exp(spec.get("vz", 0) * t)
        ww = base_w / z
        hh = ww * H / W
        x = cx + spec.get("vx", 0) * base_w * t + shake[i, 0]
        y = cy + spec.get("vy", 0) * base_w * t + shake[i, 1]
        M = np.array([[W / ww, 0, -(x - ww / 2) * W / ww], [0, H / hh, -(y - hh / 2) * H / hh]], np.float32)
        f = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        f = np.clip(f.astype(np.float32) + rng.normal(0, 1.5, f.shape), 0, 255).astype(np.uint8)
        frames.append(f)
    return frames


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(3)
    gold = []
    for si, still in enumerate(sys.argv[2:]):
        img = cv2.imread(still)
        for name, spec in MOVES.items():
            fn = f"motion_{si}_{name.replace('+', '_')}.mp4"
            frames = render(img, spec, rng)
            p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                                  "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(out / fn)], stdin=subprocess.PIPE)
            for f in frames:
                p.stdin.write(f.tobytes())
            p.stdin.close()
            p.wait()
            gold.append({"file": fn, "labels": LABELS[name], "spec": spec, "still": Path(still).name})
    (out / "gold.json").write_text(json.dumps(gold, indent=1))
    print(len(gold), "clips")


if __name__ == "__main__":
    main()
