"""Folders: the directories footage was added from, as a way to scope search ("my Disney holiday").

A folder is named by its absolute path (a prefix match) or by its name or a relative path
("Disney 2026", "Holidays/Disney 2026"), which matches that run of path segments anywhere.
A file found in several places (duplicates) belongs to every folder it was found in.
"""
from __future__ import annotations

import datetime as dt
import difflib
import posixpath
from typing import Any

from .db import Database


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(folder: str) -> str:
    """SQL LIKE pattern (ESCAPE '\\') matching file paths inside ``folder``, including subfolders."""
    f = _norm(folder.strip()).rstrip("/")
    if not f:
        raise ValueError("empty folder name")
    if f.startswith("/") or "://" in f or (len(f) > 2 and f[1] == ":"):
        return _esc(f) + "/%"
    return "%/" + _esc(f.strip("/")) + "/%"


def asset_sql(folders: list[str]) -> tuple[str, list[str]]:
    """``si.asset_id IN (...)`` clause for files inside any of ``folders``."""
    pats = [like_pattern(f) for f in folders]
    cond = " OR ".join("replace(path, '\\', '/') LIKE ? ESCAPE '\\'" for _ in pats)
    return f"si.asset_id IN (SELECT asset_id FROM asset_paths WHERE {cond})", pats


def list_folders(db: Database, q: str = "", parent: str | None = None, limit: int = 500) -> dict[str, Any]:
    """Every folder that holds footage (directly or below), with file, shot and hour counts and the date range."""
    sources = sorted(((r["id"], _norm(r["uri"]).rstrip("/")) for r in db.q("SELECT id, uri FROM sources")), key=lambda x: -len(x[1]))
    shots = {r[0]: r[1] for r in db.q("SELECT asset_id, COUNT(*) FROM shot_index GROUP BY asset_id")}
    rows = db.q("SELECT p.path, a.id, a.duration, a.mtime, json_extract(a.tech, '$.capture_date') cap FROM asset_paths p"
                " JOIN assets a ON a.id=p.asset_id WHERE a.deleted_at IS NULL")
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        path = _norm(r["path"])
        directory = posixpath.dirname(path)
        root = next((u for _, u in sources if directory == u or directory.startswith(u + "/")), None)
        if root is None:
            root = directory
        cap = str(r["cap"] or "")[:10] or dt.datetime.fromtimestamp(r["mtime"], dt.timezone.utc).date().isoformat()
        d = directory
        while True:
            e = agg.setdefault(d, {"assets": set(), "hours": 0.0, "shots": 0, "from": cap, "to": cap, "root": root, "children": set()})
            if r["id"] not in e["assets"]:
                e["assets"].add(r["id"])
                e["hours"] += (r["duration"] or 0) / 3600
                e["shots"] += shots.get(r["id"], 0)
                e["from"], e["to"] = min(e["from"], cap), max(e["to"], cap)
            if d == root or "/" not in d.strip("/"):
                break
            up = posixpath.dirname(d)
            agg.setdefault(up, {"assets": set(), "hours": 0.0, "shots": 0, "from": cap, "to": cap, "root": root, "children": set()})["children"].add(d)
            d = up
    out = []
    for d, e in agg.items():
        root_name = posixpath.basename(e["root"]) or e["root"]
        rel = root_name if d == e["root"] else root_name + "/" + d[len(e["root"]) + 1:]
        if q and q.lower() not in rel.lower():
            continue
        if parent is not None and posixpath.dirname(d) != _norm(parent).rstrip("/"):
            continue
        out.append({"path": d, "name": posixpath.basename(d) or d, "relative": rel, "source": e["root"],
                    "depth": rel.count("/"), "files": len(e["assets"]), "shots": e["shots"], "hours": round(e["hours"], 3),
                    "captured_from": e["from"], "captured_to": e["to"], "subfolders": len(e["children"])})
    out.sort(key=lambda x: x["relative"].lower())
    return {"total": len(out), "folders": out[:limit]}


def closest(db: Database, name: str, n: int = 3) -> list[str]:
    names = {f["relative"]: f["name"] for f in list_folders(db, limit=100_000)["folders"]}
    by_name = difflib.get_close_matches(name.lower(), [v.lower() for v in names.values()], n=n, cutoff=0.5)
    return [rel for rel, nm in names.items() if nm.lower() in by_name][:n]
