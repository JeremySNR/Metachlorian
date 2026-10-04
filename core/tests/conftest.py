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


def run_all(s, db) -> int:
    """Plan and run every job to completion in this process (no models: analysers that need one report unavailable)."""
    from metachlorian import pipeline
    from metachlorian.jobs import queue

    pipeline.plan_all(db, s)
    n = 0
    while True:
        job = queue.claim(db, "t")
        if not job:
            # jobs waiting on retry back-off: release them for the test
            if db.q1("SELECT COUNT(*) n FROM jobs WHERE status='queued'")["n"]:
                db.x("UPDATE jobs SET run_after=0")
                continue
            break
        pipeline.run_job(db, s, job)
        n += 1
    return n


@pytest.fixture()
def processed(lib, footage):
    """One analysed, indexed asset (three shots) in a fresh library."""
    from metachlorian.indexer import index_asset
    from metachlorian.ingest.scan import add_source, scan_source

    s, db = lib
    sid = add_source(db, str(footage))
    scan_source(db, sid)
    run_all(s, db)
    a = db.q1("SELECT * FROM assets")
    index_asset(db, s, a["id"])
    return s, db, a


# ------------------------------------------------------------------ rights matrix
# One library, analysed once per session, holding a file in every rights state. Tests that use it
# must not change it (read, search, export and package only).
RIGHTS_STATES = {
    "cleared": {"status": "cleared", "permitted_uses": ["marketing", "editorial"], "channels": ["social", "web"], "territories": ["GB", "PT"],
                "expires": "2099-01-01", "model_release": "not_applicable"},
    "editorial_only": {"status": "cleared", "permitted_uses": ["editorial"], "expires": "2099-01-01", "model_release": "not_applicable"},
    "not_cleared": {"status": "not_cleared"},
    "expired": {"status": "cleared", "permitted_uses": ["marketing", "editorial"], "expires": "2001-01-01"},
    "unknown": None,  # nothing recorded
}
MATRIX_SOURCES = {
    "cleared": ("testsrc2", "smptebars"),
    "editorial_only": ("rgbtestsrc", "testsrc"),
    "not_cleared": ("smptehdbars", "testsrc2"),
    "expired": ("yuvtestsrc", "rgbtestsrc"),
    "unknown": ("pal75bars", "smptebars"),
}


@pytest.fixture(scope="session")
def rights_matrix(tmp_path_factory):
    """A library with five files, one per rights state in RIGHTS_STATES, two shots each, plus a shot-level
    'not_cleared' override on the second shot of the cleared file. Every shot has a fake visual vector so
    similar-shot search has something to rank.

    Returns {"settings", "db", "assets": {state: asset_uid}, "shots": {state: [shot_uid, ...]},
    "override": shot_uid}; the overridden shot is listed under "cleared" too."""
    import time as _t

    import numpy as np

    from metachlorian import rights as R
    from metachlorian.indexer import index_asset
    from metachlorian.ingest.scan import add_source, scan_source

    root = tmp_path_factory.mktemp("rights_matrix")
    footage = root / "footage"
    footage.mkdir()
    for state, segs in MATRIX_SOURCES.items():
        make_video(footage / f"{state}.mp4", segments=segs, seg_s=1.5)
    s = load_settings(root / "lib", workers=0)
    s.models_dir = os.environ.get("METACHLORIAN_TEST_MODELS") or str(root / "no-models")
    s.ensure_dirs()
    db = Database(s.db_path)
    add_source(db, str(footage))
    scan_source(db, db.q1("SELECT id FROM sources")["id"])
    run_all(s, db)
    assets, shots = {}, {}
    rng = np.random.default_rng(1)
    for state, data in RIGHTS_STATES.items():
        a = db.q1("SELECT * FROM assets WHERE filename=?", (f"{state}.mp4",))
        assets[state] = a["uid"]
        rows = db.q("SELECT id, uid FROM shots WHERE asset_id=? AND active=1 ORDER BY idx", (a["id"],))
        assert len(rows) >= 2, f"{state}: expected two shots, got {len(rows)}"
        shots[state] = [r["uid"] for r in rows]
        if data:
            R.set_rights(db, a["id"], data, "fixture")
        with db.tx() as c:
            c.executemany("INSERT INTO vectors(shot_id, asset_id, space, dim, vec, created_at) VALUES(?,?,?,?,?,?)",
                          [(r["id"], a["id"], "visual", 8, (np.ones(8) + rng.normal(0, 0.05, 8)).astype(np.float16).tobytes(), _t.time())
                           for r in rows])
    cleared = db.q1("SELECT id FROM assets WHERE uid=?", (assets["cleared"],))["id"]
    override = shots["cleared"][1]
    R.set_rights(db, cleared, {"status": "not_cleared", "notes": "talent withdrew consent"}, "fixture",
                 db.q1("SELECT id FROM shots WHERE uid=?", (override,))["id"])
    for r in db.q("SELECT id FROM assets"):
        index_asset(db, s, r["id"])
    yield {"settings": s, "db": db, "assets": assets, "shots": shots, "override": override}
    db.close()


@pytest.fixture(scope="session")
def principals():
    """Every kind of caller: people by role, agents by token grant, and the solo-mode local admin."""
    from metachlorian.auth import AGENT_DEFAULT, LOCAL_ADMIN, ROLE_SCOPES, Principal

    return {
        "viewer": Principal(1, "vera", "viewer", set(ROLE_SCOPES["viewer"]), "api"),
        "editor": Principal(2, "ed", "editor", set(ROLE_SCOPES["editor"]), "api"),
        "admin": Principal(3, "ada", "admin", set(ROLE_SCOPES["admin"]), "api"),
        "agent": Principal(4, "bot", "agent", set(AGENT_DEFAULT), "mcp"),
        "agent+export": Principal(4, "bot", "agent", set(AGENT_DEFAULT) | {"media:export"}, "mcp"),
        "agent+collections": Principal(4, "bot", "agent", set(AGENT_DEFAULT) | {"collections:write"}, "mcp"),
        "agent+tags": Principal(4, "bot", "agent", set(AGENT_DEFAULT) | {"tags:write"}, "mcp"),
        "local": LOCAL_ADMIN,
    }


@pytest.fixture()
def mcp_client():
    """Factory: an in-memory MCP client session on build_server(lib), acting as `principal` (as over stdio).

        async with mcp_client(lib, principal) as client:
            res = await client.call_tool("search_shots", {...})
    """
    import contextlib

    from mcp.client.client import Client

    from metachlorian.mcp_server.server import build_server, stdio_principal

    @contextlib.asynccontextmanager
    async def connect(lib, principal):
        token = stdio_principal.set(principal)
        try:
            async with Client(build_server(lib)) as client:
                yield client
        finally:
            stdio_principal.reset(token)

    return connect
