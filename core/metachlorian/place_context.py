"""Specific place recognition and conservative continuity between camera takes.

Only direct, high-confidence evidence can anchor another shot. Inherited
labels never become anchors. Capture timestamps are camera metadata, never
filesystem mtimes. Names, evidence, gap and anchor identities remain separate
from captions so reviewers can distinguish recognition from inference.
"""
from __future__ import annotations

import datetime as dt
import math
import posixpath
import re
from collections import defaultdict
from typing import Any

from filelock import FileLock

from .db import dumps, loads, now
from .records import assign_corrections

LEVELS = ("destination", "venue", "area", "attraction_or_show")
VERSION = "1.1.0"


def capture_seconds(value: str | None) -> tuple[float, bool] | None:
    """Preserve the distinction between timezone-aware and naive camera clocks."""
    if not value:
        return None
    value = re.sub(r"^(\d{4}):(\d{2}):(\d{2})", r"\1-\2-\3", str(value)).replace("Z", "+00:00")
    try:
        date = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    aware = date.tzinfo is not None
    return date.replace(tzinfo=dt.timezone.utc).timestamp() if not aware else date.timestamp(), aware


def _norm(name: str) -> str:
    return re.sub(r"\W+", "", name.casefold())


def _direct(item: dict, row: dict, level: str) -> dict | None:
    name = str(item.get("name") or "").strip()
    confidence = item.get("confidence", "unknown")
    evidence = [str(e) for e in item.get("evidence", []) if e]
    if not name or confidence == "unknown":
        return None
    # A bare high-confidence assertion is a candidate, not an inference anchor.
    high = confidence == "high" and bool(evidence)
    relationship = item.get("relationship", "unclear")
    eligible = high and (level != "attraction_or_show" or relationship == "recording_location")
    return {"value": name, "confidence": 0.9 if high else 0.55, "method": "direct",
            "evidence": evidence, "anchor_shot_uid": row["uid"], "anchor_asset_uid": row["asset_uid"],
            "gap_seconds": 0.0, "anchor_eligible": eligible, "relationship": relationship}


def infer_places(rows: list[dict], max_gap_s: float = 30.0) -> dict[int, dict[str, dict]]:
    """Pure inference. Rows contain shots, camera times, originals flag and direct evidence.

    Across files, consider only immediate neighbours in the same folder/camera
    group and clock kind. Refuse overlaps, long gaps, conflicting evidence or
    a simultaneous camera change. Within a continuous camera original, use
    nearby shots. Probable identifications are kept but never propagated.
    """
    direct = {r["id"]: {level: value for level in LEVELS
                        if (value := _direct((r.get("recognition") or {}).get(level, {}), r, level))}
              for r in rows}
    output = {sid: dict(values) for sid, values in direct.items()}
    by_asset: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_asset[row["asset_id"]].append(row)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for shots in by_asset.values():
        r = shots[0]
        if r.get("capture") is not None and r.get("original"):
            groups[(r["folder"], r.get("camera", ""), r["capture"][1])].append(r)
    adjacent: dict[int, list[int]] = defaultdict(list)
    for group in groups.values():
        group.sort(key=lambda r: (r["capture"][0], r["asset_id"]))
        for i, row in enumerate(group):
            adjacent[row["asset_id"]] = [group[j]["asset_id"] for j in (i - 1, i + 1) if 0 <= j < len(group)]
    for target in rows:
        if not target.get("original"):
            continue
        candidates = list(by_asset[target["asset_id"]])
        for aid in adjacent[target["asset_id"]]:
            candidates += by_asset[aid]
        for level_index, level in enumerate(LEVELS):
            if level in direct[target["id"]] or level in target.get("blocked_levels", []):
                continue
            matches = []
            for anchor in candidates:
                known = direct[anchor["id"]].get(level)
                if not known or not known["anchor_eligible"] or anchor["id"] == target["id"]:
                    continue
                # Conflicting broader places invalidate narrower inheritance too.
                if any(a and b and _norm(a["value"]) != _norm(b["value"])
                       for parent in LEVELS[:level_index + 1]
                       for a, b in [(output[target["id"]].get(parent), direct[anchor["id"]].get(parent))]):
                    continue
                if anchor["asset_id"] == target["asset_id"]:
                    gap = max(target["start_s"] - anchor["end_s"], anchor["start_s"] - target["end_s"], 0.0)
                else:
                    # Gap between whole takes, not their starts or their filesystem dates.
                    left, right = sorted((anchor, target), key=lambda r: r["capture"][0])
                    gap = right["capture"][0] - (left["capture"][0] + left["asset_duration"])
                    if gap < 0:
                        continue
                    # A long recording cannot carry an early identification indefinitely.
                    distance = max(target["capture"][0] + target["start_s"] - anchor["capture"][0] - anchor["end_s"],
                                   anchor["capture"][0] + anchor["start_s"] - target["capture"][0] - target["end_s"], 0.0)
                    if distance > max_gap_s:
                        continue
                if gap <= max_gap_s:
                    def position(row):
                        return (row["capture"][0] if row.get("capture") else 0) + row["start_s"]

                    lo, hi = sorted((position(anchor), position(target)))
                    if any(lo < position(middle) < hi and any(
                        a and b and _norm(a["value"]) != _norm(b["value"])
                        for parent in LEVELS[:level_index + 1]
                        for a, b in [(direct[anchor["id"]].get(parent), direct[middle["id"]].get(parent))])
                        for middle in candidates):
                        continue
                    matches.append((gap, anchor, known))
            # Two different nearby identifications leave the shot unresolved.
            if not matches or len({_norm(m[2]["value"]) for m in matches}) != 1:
                continue
            gap, anchor, known = min(matches, key=lambda m: (m[0], m[1]["uid"]))
            output[target["id"]][level] = {**known, "method": "inherited", "anchor_eligible": False,
                "confidence": round(known["confidence"] * math.exp(-gap / 120), 3), "gap_seconds": round(gap, 3),
                "evidence": [f"Nearby camera original; inherited from {anchor['uid']} across a {gap:.1f}s gap.", *known["evidence"]]}
    return output


def refresh_places(db, settings, max_gap_s: float = 30.0) -> dict[str, int]:
    """Refresh derived signals and the search index; preserve all human corrections."""
    from .indexer import index_asset

    settings.ensure_dirs()
    with FileLock(str(settings.data_dir / "place-context.lock")):
        rows = [dict(r) for r in db.q(
            "SELECT s.*, a.uid asset_uid, a.path, a.duration asset_duration, a.tech, src.options "
            "FROM shots s JOIN assets a ON a.id=s.asset_id LEFT JOIN sources src ON src.id=a.source_id "
            "WHERE s.active=1 AND a.deleted_at IS NULL AND a.status!='missing'")]
        records = {r["target_id"]: (loads(r["value"], {}) or {}).get("place_recognition", {})
                   for r in db.q("SELECT target_id,value FROM signals WHERE name='vlm.record' AND source='caption'")}
        corrections = defaultdict(list)
        for r in db.q("SELECT * FROM corrections WHERE active=1 AND level='shot' ORDER BY id"):
            corrections[r["asset_uid"]].append(dict(r))
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["asset_uid"]].append(row)
        manual = {}
        for uid, shots in grouped.items():
            manual.update(assign_corrections(shots, corrections[uid]))
        for row in rows:
            tech = loads(row["tech"], {}) or {}
            options = loads(row["options"], {}) or {}
            row["capture"] = capture_seconds(tech.get("capture_date"))
            row["folder"] = posixpath.dirname(row["path"].replace("\\", "/"))
            row["camera"] = "|".join(str(tech.get(k) or "") for k in ("camera_make", "camera_model"))
            row["original"] = bool(options.get("camera_originals"))
            row["recognition"] = dict(records.get(row["id"], {}))
            row["blocked_levels"] = []
            for c in manual.get(row["id"], []):
                level = c["field"].removeprefix("content.")
                if level in LEVELS and c["op"] == "set":
                    name = loads(c["value"], "")
                    row["recognition"][level] = {"name": name, "confidence": "high",
                                               "relationship": "recording_location",
                                               "evidence": [f"Confirmed by {c['actor']}: {c['note'] or 'manual correction'}"]}
                    if not name:
                        row["blocked_levels"].append(level)
        results = infer_places(rows, max_gap_s)
        desired = {(row["id"], f"content.{level}"): (row["asset_id"], value)
                   for row in rows for level, value in results[row["id"]].items()}
        existing = {(r["target_id"], r["name"]): (r["asset_id"], loads(r["value"])) for r in
                    db.q("SELECT * FROM signals WHERE source='place_context'")}
        changed = {key for key in desired.keys() | existing.keys() if desired.get(key) != existing.get(key)}
        assets = set()
        with db.tx() as c:
            for sid, field in changed:
                c.execute("DELETE FROM signals WHERE source='place_context' AND target_id=? AND name=?", (sid, field))
                pair = desired.get((sid, field)) or existing[(sid, field)]
                assets.add(pair[0])
                if (sid, field) in desired:
                    aid, value = desired[(sid, field)]
                    c.execute("INSERT INTO signals(level,target_id,asset_id,name,value,source,confidence,model_version,created_at) "
                              "VALUES('shot',?,?,?,?,?,?,?,?)", (sid, aid, field, dumps(value), "place_context", value["confidence"], VERSION, now()))
        for aid in assets:
            index_asset(db, settings, aid)
        return {"changed_fields": len(changed), "reindexed_assets": len(assets),
                "direct_fields": sum(v["method"] == "direct" for _, v in desired.values()),
                "inherited_fields": sum(v["method"] == "inherited" for _, v in desired.values())}
