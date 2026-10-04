"""People: clusters of face embeddings ("identities") that a person can name, merge and correct.

Faces are assigned to the nearest identity centroid when the cosine similarity clears ``MATCH``
(SFace's published same-person threshold is 0.363 on aligned faces; a centroid is steadier than
a single face, so we use a slightly stricter value to avoid merging strangers). Otherwise a new,
unnamed identity is created. Human decisions — naming, merging, moving a face, "not this person" —
are never undone by automatic assignment and survive re-analysis (re-attached by time and box).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import numpy as np

from .db import Database, now
from .media.faceid import iou

MATCH = 0.42
SAME_FACE_IN_SHOT = 0.55


def _vec(blob: bytes, dtype=np.float32) -> np.ndarray:
    v = np.frombuffer(blob, dtype=dtype).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def replace_asset_faces(c: sqlite3.Connection, asset_id: int, faces: list[dict[str, Any]]) -> None:
    """Swap an asset's faces for a fresh analysis, keeping human decisions, then assign identities."""
    old = [dict(r) for r in c.execute("SELECT t, box, embedding, identity_id, assigned_by, excluded_identity FROM faces WHERE asset_id=? AND "
                                      "(assigned_by IN ('human','named') OR excluded_identity IS NOT NULL)", (asset_id,))]
    for o in old:
        o["box"], o["emb"], o["used"] = json.loads(o["box"]), _vec(o["embedding"], np.float16), False
    c.execute("DELETE FROM faces WHERE asset_id=?", (asset_id,))
    ts = now()
    for f in faces:
        e = np.asarray(f["embedding"], dtype=np.float32)
        e = e / (np.linalg.norm(e) + 1e-9)
        # The same face as before: close in time, overlapping box, similar embedding. Each decision is used once.
        cands = [(iou(o["box"], f["box"]), -abs(o["t"] - f["t"]), k) for k, o in enumerate(old)
                 if not o["used"] and abs(o["t"] - f["t"]) <= 0.25 and float(o["emb"] @ e) >= 0.5]
        cands = [x for x in cands if x[0] >= 0.4]
        keep = old[max(cands)[2]] if cands else None
        if keep:
            keep["used"] = True
        manual = bool(keep) and keep["assigned_by"] in ("human", "named")
        c.execute("INSERT INTO faces(asset_id, shot_id, t, box, score, size_px, appearances, thumb, embedding, identity_id, assigned_by,"
                  " excluded_identity, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (asset_id, f["shot_id"], f["t"], json.dumps(f["box"]), f["score"], f["size_px"], f.get("appearances", 1), f["thumb"],
                   e.astype(np.float16).tobytes(),
                   keep["identity_id"] if manual else None,
                   keep["assigned_by"] if manual else "auto",
                   keep["excluded_identity"] if keep else None, ts))
    assign(c, asset_id)


def assign(c: sqlite3.Connection, asset_id: int | None = None) -> int:
    """Give unassigned faces an identity: the nearest centroid above MATCH, else a new identity."""
    ids, cents, counts = [], [], []
    for r in c.execute("SELECT id, centroid, n FROM identities"):
        ids.append(r["id"])
        cents.append(_vec(r["centroid"]))
        counts.append(r["n"])
    mat = np.stack(cents) if cents else np.zeros((0, 128), np.float32)
    where = "identity_id IS NULL" + (" AND asset_id=?" if asset_id is not None else "")
    rows = c.execute(f"SELECT id, embedding, excluded_identity FROM faces WHERE {where} ORDER BY size_px DESC, score DESC",
                     (asset_id,) if asset_id is not None else ()).fetchall()
    ts = now()
    changed: dict[int, None] = {}
    for r in rows:
        e = _vec(r["embedding"], np.float16)
        best, sim = None, -1.0
        if len(ids):
            sims = mat @ e
            if r["excluded_identity"] in ids:
                sims[ids.index(r["excluded_identity"])] = -1.0
            j = int(np.argmax(sims))
            best, sim = j, float(sims[j])
        if best is not None and sim >= MATCH:
            n = counts[best]
            cen = mat[best] * n + e
            mat[best] = cen / (np.linalg.norm(cen) + 1e-9)
            counts[best] = n + 1
            c.execute("UPDATE faces SET identity_id=? WHERE id=?", (ids[best], r["id"]))
            changed[best] = None
        else:
            cur = c.execute("INSERT INTO identities(centroid, n, cover_face_id, created_at, updated_at) VALUES(?,?,?,?,?)",
                            (e.astype(np.float32).tobytes(), 1, r["id"], ts, ts))
            ids.append(cur.lastrowid)
            counts.append(1)
            mat = np.vstack([mat, e[None, :]])
            c.execute("UPDATE faces SET identity_id=? WHERE id=?", (cur.lastrowid, r["id"]))
    for j in changed:
        c.execute("UPDATE identities SET centroid=?, n=?, updated_at=? WHERE id=?", (mat[j].astype(np.float32).tobytes(), counts[j], ts, ids[j]))
        frows = c.execute("SELECT id, embedding, size_px, score FROM faces WHERE identity_id=? ORDER BY size_px DESC LIMIT 200", (ids[j],)).fetchall()
        if frows:
            embs = np.stack([_vec(r["embedding"], np.float16) for r in frows])
            c.execute("UPDATE identities SET cover_face_id=? WHERE id=?", (_cover(frows, embs, mat[j]), ids[j]))
    return len(rows)


def _recompute(c: sqlite3.Connection, identity_id: int) -> None:
    rows = c.execute("SELECT id, embedding, size_px, score FROM faces WHERE identity_id=? ORDER BY size_px DESC, score DESC LIMIT 500",
                     (identity_id,)).fetchall()
    if not rows:
        return
    embs = np.stack([_vec(r["embedding"], np.float16) for r in rows])
    m = embs.mean(axis=0)
    m = m / (np.linalg.norm(m) + 1e-9)
    c.execute("UPDATE identities SET centroid=?, n=?, cover_face_id=?, updated_at=? WHERE id=?",
              (m.astype(np.float32).tobytes(), len(rows), _cover(rows, embs, m), now(), identity_id))


def _cover(rows, embs: np.ndarray, centroid: np.ndarray) -> int:
    """The most typical face (closest to the centroid), preferring larger, clearer ones among near ties."""
    sims = embs @ centroid
    best = max(range(len(rows)), key=lambda k: (round(float(sims[k]), 2), rows[k]["size_px"] * rows[k]["score"]))
    return rows[best]["id"]


def assets_of(db: Database, identity_ids: list[int]) -> list[int]:
    q = ",".join("?" * len(identity_ids))
    return [r[0] for r in db.q(f"SELECT DISTINCT asset_id FROM faces WHERE identity_id IN ({q})", identity_ids)]


def rename(db: Database, identity_id: int, name: str, actor: str) -> None:
    name = " ".join((name or "").split())[:80]
    with db.tx() as c:
        if not c.execute("SELECT 1 FROM identities WHERE id=?", (identity_id,)).fetchone():
            raise KeyError(identity_id)
        if name:
            other = c.execute("SELECT id FROM identities WHERE lower(name)=lower(?) AND id<>?", (name, identity_id)).fetchone()
            if other:
                raise ValueError(f"{name} is already person {other['id']}; merge the two instead of giving them the same name")
            # Naming confirms the cluster: its faces are no longer moved by automatic assignment.
            c.execute("UPDATE faces SET assigned_by='named' WHERE identity_id=? AND assigned_by='auto'", (identity_id,))
        else:
            # Un-naming undoes only what naming confirmed; individual moves and merges stay.
            c.execute("UPDATE faces SET assigned_by='auto' WHERE identity_id=? AND assigned_by='named'", (identity_id,))
        c.execute("UPDATE identities SET name=?, named_by=?, updated_at=? WHERE id=?", (name or None, actor if name else "", now(), identity_id))


def merge(db: Database, source_id: int, into_id: int) -> None:
    if source_id == into_id:
        raise ValueError("cannot merge a person into themselves")
    with db.tx() as c:
        src = c.execute("SELECT name FROM identities WHERE id=?", (source_id,)).fetchone()
        dst = c.execute("SELECT name FROM identities WHERE id=?", (into_id,)).fetchone()
        if not src or not dst:
            raise KeyError(source_id if not src else into_id)
        c.execute("UPDATE faces SET identity_id=?, assigned_by='human' WHERE identity_id=?", (into_id, source_id))
        if not dst["name"] and src["name"]:
            c.execute("UPDATE identities SET name=? WHERE id=?", (src["name"], into_id))
        c.execute("DELETE FROM identities WHERE id=?", (source_id,))
        _recompute(c, into_id)


def move_face(db: Database, face_id: int, identity_id: int | None) -> int | None:
    """Put a face on another person (``identity_id``), or None for "not this person" (a new person)."""
    with db.tx() as c:
        f = c.execute("SELECT identity_id FROM faces WHERE id=?", (face_id,)).fetchone()
        if not f:
            raise KeyError(face_id)
        old = f["identity_id"]
        if identity_id is not None:
            if not c.execute("SELECT 1 FROM identities WHERE id=?", (identity_id,)).fetchone():
                raise KeyError(identity_id)
            c.execute("UPDATE faces SET identity_id=?, assigned_by='human', excluded_identity=NULL WHERE id=?", (identity_id, face_id))
            target = identity_id
        else:
            row = c.execute("SELECT embedding FROM faces WHERE id=?", (face_id,)).fetchone()
            ts = now()
            cur = c.execute("INSERT INTO identities(centroid, n, cover_face_id, created_at, updated_at) VALUES(?,?,?,?,?)",
                            (_vec(row["embedding"], np.float16).astype(np.float32).tobytes(), 1, face_id, ts, ts))
            target = cur.lastrowid
            c.execute("UPDATE faces SET identity_id=?, assigned_by='human', excluded_identity=? WHERE id=?", (target, old, face_id))
        if old is not None:
            if c.execute("SELECT COUNT(*) FROM faces WHERE identity_id=?", (old,)).fetchone()[0]:
                _recompute(c, old)
            else:
                c.execute("DELETE FROM identities WHERE id=? AND name IS NULL", (old,))
        _recompute(c, target)
    return target


def forget(db: Database, identity_id: int) -> tuple[list[int], list[str]]:
    """Delete a person and every face embedding assigned to them.
    Returns the affected assets (to re-index) and the face crops to delete from disk."""
    affected = assets_of(db, [identity_id])
    with db.tx() as c:
        if not c.execute("SELECT 1 FROM identities WHERE id=?", (identity_id,)).fetchone():
            raise KeyError(identity_id)
        thumbs = [r[0] for r in c.execute("SELECT a.uid || '/' || f.thumb FROM faces f JOIN assets a ON a.id=f.asset_id WHERE f.identity_id=?",
                                          (identity_id,))]
        c.execute("DELETE FROM faces WHERE identity_id=?", (identity_id,))
        c.execute("DELETE FROM identities WHERE id=?", (identity_id,))
    return affected, thumbs


def list_people(db: Database, q: str = "", named: bool | None = None, limit: int = 200, offset: int = 0) -> dict[str, Any]:
    where, args = ["cnt.n > 0"], []
    if q:
        where.append("i.name LIKE ?")
        args.append(f"%{q}%")
    if named is True:
        where.append("i.name IS NOT NULL")
    elif named is False:
        where.append("i.name IS NULL")
    base = (" FROM identities i JOIN (SELECT identity_id, COUNT(*) n, COUNT(DISTINCT shot_id) shots, COUNT(DISTINCT asset_id) files"
            " FROM faces GROUP BY identity_id) cnt ON cnt.identity_id=i.id WHERE " + " AND ".join(where))
    total = db.q1("SELECT COUNT(*) n" + base, args)["n"]
    rows = db.q("SELECT i.id, i.name, i.named_by, i.cover_face_id, cnt.n faces, cnt.shots, cnt.files" + base +
                " ORDER BY (i.name IS NULL), cnt.shots DESC, i.id LIMIT ? OFFSET ?", (*args, limit, offset))
    out = []
    for r in rows:
        cover = db.q1("SELECT f.thumb, a.uid FROM faces f JOIN assets a ON a.id=f.asset_id WHERE f.id=?", (r["cover_face_id"],)) if r["cover_face_id"] else None
        if not cover:
            cover = db.q1("SELECT f.thumb, a.uid FROM faces f JOIN assets a ON a.id=f.asset_id WHERE f.identity_id=? ORDER BY f.size_px DESC LIMIT 1", (r["id"],))
        out.append({"id": r["id"], "name": r["name"], "label": r["name"] or f"Person {r['id']}", "named": bool(r["name"]),
                    "faces": r["faces"], "shots": r["shots"], "files": r["files"],
                    "cover": f"/media/{cover['uid']}/{cover['thumb']}" if cover else None})
    return {"total": total, "people": out}


def person_faces(db: Database, identity_id: int, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    rows = db.q("SELECT f.id, f.t, f.box, f.score, f.size_px, f.thumb, f.assigned_by, s.uid shot_uid, s.idx, a.uid asset_uid, a.filename, a.fps"
                " FROM faces f JOIN shots s ON s.id=f.shot_id JOIN assets a ON a.id=f.asset_id WHERE f.identity_id=?"
                " ORDER BY a.filename, f.t LIMIT ? OFFSET ?", (identity_id, limit, offset))
    return [{"id": r["id"], "t": r["t"], "box": json.loads(r["box"]), "score": r["score"], "size_px": r["size_px"],
             "thumb": f"/media/{r['asset_uid']}/{r['thumb']}", "confirmed": r["assigned_by"] in ("human", "named"), "fps": r["fps"],
             "shot_uid": r["shot_uid"], "shot_number": r["idx"] + 1, "asset_uid": r["asset_uid"], "filename": r["filename"]} for r in rows]


def shot_people(db: Database, asset_id: int) -> dict[int, list[dict[str, Any]]]:
    """Identities per shot of an asset, for shot records and the index."""
    out: dict[int, list[dict[str, Any]]] = {}
    for r in db.q("SELECT f.shot_id, f.identity_id, i.name, MAX(f.size_px) px, SUM(f.appearances) n FROM faces f"
                  " JOIN identities i ON i.id=f.identity_id WHERE f.asset_id=? GROUP BY f.shot_id, f.identity_id ORDER BY px DESC", (asset_id,)):
        out.setdefault(r["shot_id"], []).append({"id": r["identity_id"], "name": r["name"], "label": r["name"] or f"Person {r['identity_id']}"})
    return out


def names(db: Database) -> dict[str, int]:
    return {r["name"].lower(): r["id"] for r in db.q("SELECT id, name FROM identities WHERE name IS NOT NULL")}
