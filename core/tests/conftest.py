from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from metachlorian.config import load_settings
from metachlorian.db import Database


def make_video(path: Path, segments=("testsrc2", "smptebars", "rgbtestsrc"), seg_s: float = 2.0, size="320x180", rate=25,
               audio: bool = True) -> Path:
    """A short video with hard cuts between visually distinct synthetic sources."""
    inputs, filters = [], []
    for i, src in enumerate(segments):
        inputs += ["-f", "lavfi", "-i", f"{src}=size={size}:rate={rate}:duration={seg_s}"]
        filters.append(f"[{i}:v]format=yuv420p,setsar=1[v{i}]")
    n = len(segments)
    fc = ";".join(filters) + ";" + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    args = ["ffmpeg", "-y", "-v", "error", *inputs]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seg_s * n}"]
    args += ["-filter_complex", fc, "-map", "[v]"]
    if audio:
        args += ["-map", f"{n}:a", "-c:a", "aac"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(args, check=True)
    return path


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("media")
    return make_video(d / "three_cuts.mp4")


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    models = os.environ.get("METACHLORIAN_TEST_MODELS")
    if models:
        monkeypatch.setenv("METACHLORIAN_MODELS", models)
    else:
        monkeypatch.setenv("METACHLORIAN_MODELS", str(tmp_path / "no-models"))
    s = load_settings(tmp_path / "lib", workers=0)
    s.ensure_dirs()
    db = Database(s.db_path)
    yield s, db
    db.close()


@pytest.fixture()
def footage(tmp_path, sample_video) -> Path:
    d = tmp_path / "footage"
    d.mkdir()
    shutil.copy(sample_video, d / "clip_a.mp4")
    return d
