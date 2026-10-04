"""Effective records: machine signals overlaid with human corrections.

Precedence per field: human correction > fusion > the most confident other
analyser. Corrections are stored separately (``corrections`` table) and are
re-applied every time a record is built, so re-processing never loses them.
They are anchored by shot uid and by time span: if a new segmentation removes
the shot, the correction re-attaches to the shot that overlaps it most.
"""
from __future__ import annotations

from typing import Any

from .db import Database, dumps, loads, now
from .vocab import registry

# Fields that hold controlled-vocabulary terms, and their vocabulary.
VOCAB_FIELDS = {
    "camera.movement": ("camera_movement", True),
    "camera.shot_size": ("shot_size", False),
    "camera.angle": ("camera_angle", False),
    "camera.speed_effect": ("speed_effect", True),
    "shot.role": ("shot_role", True),
    "content.setting": ("setting", True),
    "content.time_of_day": ("time_of_day", False),
    "content.weather": ("weather", True),
    "content.season": ("season", False),
    "semantic.mood": ("mood", True),
    "pacing.pace": ("pace", False),
    "audio.classes": ("audio_class", True),
    "quality.flags": ("quality_flag", True),
}
# Free-text term lists (not controlled, but faceted).
FREE_TERM_FIELDS = {"content.objects": "object", "semantic.topics": "topic", "content.concepts": "concept",
                    "content.activities": "activity", "semantic.suggested_uses": "use"}
# Fields a person may correct, with their kind.
CORRECTABLE: dict[str, str] = {**{k: ("terms" if multi else "term") for k, (_, multi) in VOCAB_FIELDS.items()},
                               **{k: "terms" for k in FREE_TERM_FIELDS},
                               "content.caption": "text", "content.summary": "text", "content.location": "text",
                               "people.count": "int", "quality.usable": "bool", "people.talking_to_camera": "bool",
                               "content.ocr_text": "text", "audio.transcript": "text", "tags": "terms"}
ASSET_CORRECTABLE = {"structure.edit_type": "term", "content.location": "text", "semantic.summary": "text", "title": "text",
                     "tags": "terms", "capture_date": "text"}


def _norm_value(v: Any) -> Any:
    return v


def _rank(source: str) -> int:
    return {"human": 3, "fusion": 2}.get(source, 1)


def collect(db: Database, level: str, target_id: int) -> dict[str, dict[str, Any]]:
    """Best machine value per signal name, with provenance."""
    rows = db.q("SELECT name, value, source, confidence, model_version, created_at FROM signals WHERE level=? AND target_id=?", (level, target_id))
    best: dict[str, dict[str, Any]] = {}
    for r in rows:
        cand = {"value": loads(r["value"]), "source": r["source"], "confidence": r["confidence"], "model_version": r["model_version"]}
        cur = best.get(r["name"])
        if cur is None or (_rank(cand["source"]), cand["confidence"] or 0) > (_rank(cur["source"]), cur["confidence"] or 0):
            if cur is not None:
                cand.setdefault("alternatives", cur.get("alternatives", []) + [{k: cur[k] for k in ("source", "confidence", "value")}])
            best[r["name"]] = cand
        else:
            cur.setdefault("alternatives", []).append({k: cand[k] for k in ("source", "confidence", "value")})
    return best


def corrections_for_asset(db: Database, asset_uid: str) -> list[dict[str, Any]]:
    return [dict(r) for r in db.q("SELECT * FROM corrections WHERE asset_uid=? AND active=1 ORDER BY id", (asset_uid,))]


def assign_corrections(shots: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_uid = {s["uid"]: s["id"] for s in shots}
    out: dict[int, list[dict[str, Any]]] = {}
    for c in corrections:
        if c["level"] != "shot":
            continue
        sid = by_uid.get(c["shot_uid"])
        if sid is None and c["anchor_start"] is not None:
            best, best_ov = None, 0.0
            for s in shots:
                ov = min(s["end_s"], c["anchor_end"]) - max(s["start_s"], c["anchor_start"])
                if ov > best_ov:
                    best, best_ov = s["id"], ov
            sid = best
        if sid is not None:
            out.setdefault(sid, []).append(c)
    return out


def apply_corrections(fields: dict[str, dict[str, Any]], corrections: list[dict[str, Any]]) -> None:
    for c in corrections:
        name, op, val = c["field"], c["op"], loads(c["value"])
        cur = fields.get(name)
        machine = cur["value"] if cur else None
        prov = {"source": "human", "confidence": 1.0, "model_version": "human", "corrected": True,
                "corrected_by": c["actor"], "corrected_at": c["created_at"], "correction_id": c["id"], "note": c["note"]}
        if op == "set":
            if CORRECTABLE.get(name) == "term" or VOCAB_FIELDS.get(name, (None, True))[1] is False:
                newv = {"term": val, "confidence": 1.0, "sources": ["human"]} if isinstance(val, str) else val
            elif isinstance(val, list):
                newv = [{"term": t, "confidence": 1.0, "sources": ["human"]} if isinstance(t, str) else t for t in val]
            elif CORRECTABLE.get(name) in ("text", "int", "bool"):
                newv = {"value": val, "confidence": 1.0, "sources": ["human"]}
            else:
                newv = val
            fields[name] = {"value": newv, **prov, "machine": machine}
        elif op in ("add", "remove"):
            items = list(machine) if isinstance(machine, list) else []
            items = [dict(i) if isinstance(i, dict) else {"term": i, "confidence": 1.0} for i in items]
            if op == "add":
                items = [i for i in items if i["term"] != val] + [{"term": val, "confidence": 1.0, "sources": ["human"]}]
            else:
                items = [i for i in items if i["term"] != val]
            base_machine = cur.get("machine", machine) if cur else machine
            fields[name] = {"value": items, **prov, "machine": base_machine}


def term_list(v: Any) -> list[dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, dict) and "term" in v:
        return [v]
    if isinstance(v, list):
        return [x if isinstance(x, dict) else {"term": x, "confidence": 1.0} for x in v]
    return []


def scalar(v: Any) -> Any:
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    if isinstance(v, dict) and "term" in v:
        return v["term"]
    return v


def shot_rows(db: Database, asset_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in db.q("SELECT * FROM shots WHERE asset_id=? AND active=1 ORDER BY idx", (asset_id,))]


def build_asset_doc(db: Database, asset_id: int) -> dict[str, Any]:
    a = db.q1("SELECT * FROM assets WHERE id=?", (asset_id,))
    if not a:
        raise KeyError(asset_id)
    fields = collect(db, "asset", asset_id)
    corr = [c for c in corrections_for_asset(db, a["uid"]) if c["level"] == "asset"]
    apply_corrections(fields, corr)
    summary = loads(a["summary"], {}) or {}
    tech = loads(a["tech"], {}) or {}
    edit = fields.get("structure.edit_type", {}).get("value") or summary.get("edit_type")
    return {
        "uid": a["uid"], "id": a["id"], "filename": a["filename"], "path": a["path"], "status": a["status"],
        "size": a["size"], "duration": a["duration"], "width": a["width"], "height": a["height"], "fps": a["fps"],
        "created_at": a["created_at"], "updated_at": a["updated_at"], "technical": tech, "structure": summary,
        "edit_type": edit, "fields": fields,
        "title": scalar(fields["title"]["value"]) if "title" in fields else None,
        "location": scalar(fields["content.location"]["value"]) if "content.location" in fields else None,
    }


def build_shot_docs(db: Database, asset_id: int) -> list[dict[str, Any]]:
    asset = build_asset_doc(db, asset_id)
    shots = shot_rows(db, asset_id)
    corr = assign_corrections(shots, corrections_for_asset(db, asset["uid"]))
    out = []
    moments = {}
    for m in db.q("SELECT * FROM moments WHERE asset_id=? ORDER BY start_s", (asset_id,)):
        moments.setdefault(m["shot_id"], []).append(m)
    for s in shots:
        fields = collect(db, "shot", s["id"])
        apply_corrections(fields, corr.get(s["id"], []))
        out.append(shot_doc(asset, s, fields, moments.get(s["id"], [])))
    return out


def build_shot_doc(db: Database, shot_id: int) -> dict[str, Any]:
    s = db.q1("SELECT * FROM shots WHERE id=?", (shot_id,))
    if not s:
        raise KeyError(shot_id)
    asset = build_asset_doc(db, s["asset_id"])
    shots = shot_rows(db, s["asset_id"])
    corr = assign_corrections(shots or [dict(s)], corrections_for_asset(db, asset["uid"]))
    fields = collect(db, "shot", shot_id)
    apply_corrections(fields, corr.get(shot_id, []))
    moms = db.q("SELECT * FROM moments WHERE shot_id=? ORDER BY start_s", (shot_id,))
    return shot_doc(asset, dict(s), fields, moms)


def shot_doc(asset: dict[str, Any], s: dict[str, Any], fields: dict[str, dict[str, Any]], moments: list) -> dict[str, Any]:
    kfs = loads(s["keyframes"], []) or []
    poster = next((k for k in kfs if k.get("poster")), kfs[len(kfs) // 2] if kfs else None)
    tech = asset["technical"]
    doc = {
        "uid": s["uid"], "id": s["id"], "asset_uid": asset["uid"], "asset_id": asset["id"], "filename": asset["filename"],
        "path": asset["path"], "idx": s["idx"], "start": round(s["start_s"], 3), "end": round(s["end_s"], 3),
        "duration": round(s["end_s"] - s["start_s"], 3), "start_frame": s["start_frame"], "end_frame": s["end_frame"],
        "kind": s["kind"], "transition_in": s["transition_in"], "keyframes": kfs,
        "poster": poster["file"] if poster else None, "thumb": f"kf/{s['idx']:05d}_thumb.jpg" if kfs else None,
        "technical": {k: tech.get(k) for k in ("width", "height", "fps", "aspect_ratio", "orientation", "resolution_class", "video_codec",
                                               "bit_depth", "hdr", "hdr_format", "color_transfer", "camera_make", "camera_model", "lens",
                                               "capture_date", "gps", "audio_channels")},
        "edit_type": asset.get("edit_type"),
        "fields": fields,
        "moments": [{"kind": m["kind"], "start": m["start_s"], "end": m["end_s"], "text": m["text"], "confidence": m["confidence"],
                     "source": m["source"], "data": {k: v for k, v in (loads(m["data"], {}) or {}).items() if k != "words"}} for m in moments],
    }
    log = fields.get("look.log_likeness", {}).get("value") or 0
    doc["technical"]["log_profile"] = bool(tech.get("log_hint")) or log >= 0.6
    doc["technical"]["log_confidence"] = 0.9 if tech.get("log_hint") else round(float(log), 3)
    return doc


def record_correction(db: Database, level: str, asset_uid: str, field: str, op: str, value: Any, actor: str, user_id: int | None,
                      shot_uid: str | None = None, note: str = "") -> int:
    if level == "shot":
        allowed = CORRECTABLE
    else:
        allowed = ASSET_CORRECTABLE
    if field not in allowed:
        raise ValueError(f"'{field}' cannot be corrected. Correctable fields: {sorted(allowed)}")
    if op not in ("set", "add", "remove"):
        raise ValueError("op must be set, add or remove")
    kind = allowed[field]
    vocab = VOCAB_FIELDS.get(field, (None,))[0] if level == "shot" else ("edit_type" if field == "structure.edit_type" else None)
    if vocab:
        reg = registry()
        vals = value if isinstance(value, list) else [value]
        for v in vals:
            if not reg.valid(vocab, v):
                raise ValueError(f"'{v}' is not a term in the {vocab} vocabulary")
    if kind == "int" and not isinstance(value, int):
        raise ValueError(f"{field} needs an integer")
    if kind == "bool" and not isinstance(value, bool):
        raise ValueError(f"{field} needs true or false")
    anchor = (None, None)
    if shot_uid:
        s = db.q1("SELECT start_s, end_s FROM shots WHERE uid=?", (shot_uid,))
        if not s:
            raise KeyError(shot_uid)
        anchor = (s["start_s"], s["end_s"])
    with db.tx() as c:
        if op == "set":
            # A new 'set' supersedes earlier corrections of the same field.
            c.execute("UPDATE corrections SET active=0 WHERE asset_uid=? AND IFNULL(shot_uid,'')=IFNULL(?, '') AND field=? AND active=1",
                      (asset_uid, shot_uid, field))
        cur = c.execute("INSERT INTO corrections(level, asset_uid, shot_uid, anchor_start, anchor_end, field, op, value, note, user_id, actor, created_at)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (level, asset_uid, shot_uid, anchor[0], anchor[1], field, op, dumps(value), note, user_id, actor, now()))
        return cur.lastrowid


def revert_correction(db: Database, correction_id: int) -> None:
    db.x("UPDATE corrections SET active=0 WHERE id=?", (correction_id,))
