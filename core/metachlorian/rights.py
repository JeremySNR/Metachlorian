"""Rights and clearance.

Rights are recorded per asset and can be overridden per shot. A use check
returns one of: allowed, restricted (needs a human decision), blocked, or
unknown (nothing recorded). Search with an intended use returns only
``allowed`` shots unless the caller explicitly asks for more.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .db import Database, dumps, loads, now
from .vocab import registry

FIELDS = ("source", "owner", "licence", "status", "permitted_uses", "channels", "territories", "excluded_territories", "starts",
          "expires", "model_release", "property_release", "brand_safety", "attribution", "notes")
LIST_FIELDS = {"permitted_uses", "channels", "territories", "excluded_territories"}
STATUSES = ("cleared", "restricted", "not_cleared", "unknown")
# Uses where identifiable people need a model release.
RELEASE_USES = {"commercial", "advertising", "marketing", "merchandise"}
OK_RELEASES = {"unlimited", "not_applicable"}


def empty() -> dict[str, Any]:
    return {"status": "unknown", "source": "", "owner": "", "licence": "", "permitted_uses": [], "channels": [], "territories": [],
            "excluded_territories": [], "starts": None, "expires": None, "model_release": "unknown", "property_release": "unknown",
            "brand_safety": "unknown", "attribution": "", "notes": "", "level": "none"}


def _row(r) -> dict[str, Any]:
    d = {k: r[k] for k in FIELDS}
    for k in LIST_FIELDS:
        d[k] = loads(d[k], [])
    d["updated_by"], d["updated_at"] = r["updated_by"], r["updated_at"]
    return d


def get_rights(db: Database, asset_id: int, shot_id: int | None = None) -> dict[str, Any]:
    if shot_id is not None:
        r = db.q1("SELECT * FROM rights WHERE asset_id=? AND shot_id=?", (asset_id, shot_id))
        if r:
            base = get_rights(db, asset_id, None)
            d = _row(r)
            # Shot override: empty values inherit from the asset.
            merged = {k: (d[k] if d[k] not in (None, "", [], "unknown") else base.get(k)) for k in FIELDS}
            merged["status"] = d["status"] if d["status"] != "unknown" else base["status"]
            merged.update({"level": "shot", "updated_by": d["updated_by"], "updated_at": d["updated_at"]})
            return merged
    r = db.q1("SELECT * FROM rights WHERE asset_id=? AND shot_id IS NULL", (asset_id,))
    if not r:
        return empty()
    d = _row(r)
    d["level"] = "asset"
    return d


def set_rights(db: Database, asset_id: int, data: dict[str, Any], actor: str, shot_id: int | None = None) -> dict[str, Any]:
    reg = registry()
    clean: dict[str, Any] = {}
    for k, v in data.items():
        if k not in FIELDS:
            continue
        if k in LIST_FIELDS:
            v = [str(x).strip() for x in (v or []) if str(x).strip()]
            vocab = {"permitted_uses": "usage", "channels": "channel"}.get(k)
            if vocab:
                bad = [x for x in v if not reg.valid(vocab, x)]
                if bad:
                    raise ValueError(f"unknown {vocab} terms: {bad}")
            if k in ("territories", "excluded_territories"):
                v = [x.upper() for x in v]
                bad = [x for x in v if not (len(x) == 2 and x.isalpha())]
                if bad:
                    raise ValueError(f"territories must be ISO 3166-1 alpha-2 codes or WW: {bad}")
        elif k == "status" and v not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        elif k in ("model_release", "property_release") and v and not reg.valid("release_status", v):
            raise ValueError(f"{k} must be a release_status term")
        elif k in ("starts", "expires") and v:
            dt.date.fromisoformat(str(v)[:10])
            v = str(v)[:10]
        clean[k] = v
    cur = db.q1("SELECT * FROM rights WHERE asset_id=? AND shot_id IS ?", (asset_id, shot_id))
    base = _row(cur) if cur else {k: v for k, v in empty().items() if k in FIELDS}
    base.update(clean)
    vals = [dumps(base[k]) if k in LIST_FIELDS else base[k] for k in FIELDS]
    with db.tx() as c:
        if cur:
            c.execute(f"UPDATE rights SET {', '.join(f'{k}=?' for k in FIELDS)}, updated_by=?, updated_at=? WHERE id=?", (*vals, actor, now(), cur["id"]))
        else:
            c.execute(f"INSERT INTO rights(asset_id, shot_id, {', '.join(FIELDS)}, updated_by, updated_at) VALUES(?,?,{','.join('?' * len(FIELDS))},?,?)",
                      (asset_id, shot_id, *vals, actor, now()))
    return get_rights(db, asset_id, shot_id)


def _covers(allowed: list[str], wanted: str | None, vocab: str) -> bool:
    if not allowed or not wanted:
        return True
    v = registry().get(vocab)
    return any(wanted in v.narrower(a) for a in allowed if a in v.terms) or wanted in allowed


def check(r: dict[str, Any], use: str | None = None, channel: str | None = None, territory: str | None = None,
          on: str | None = None, people_visible: bool = False) -> dict[str, Any]:
    """Verdict for an intended use. Every reason is explained."""
    reasons: list[str] = []
    day = dt.date.fromisoformat(on[:10]) if on else dt.date.today()
    status = r.get("status", "unknown")
    if status == "unknown":
        return {"verdict": "unknown", "reasons": ["No rights information has been recorded."], "rights": r}
    if status == "not_cleared":
        return {"verdict": "blocked", "reasons": ["Marked as not cleared."], "rights": r}
    blocked = False
    if r.get("expires") and dt.date.fromisoformat(r["expires"]) < day:
        blocked = True
        reasons.append(f"Licence expired on {r['expires']}.")
    if r.get("starts") and dt.date.fromisoformat(r["starts"]) > day:
        blocked = True
        reasons.append(f"Licence starts on {r['starts']}.")
    if use and not _covers(r.get("permitted_uses") or [], use, "usage"):
        blocked = True
        reasons.append(f"Use '{use}' is not permitted (allowed: {', '.join(r['permitted_uses'])}).")
    if channel and not _covers(r.get("channels") or [], channel, "channel"):
        blocked = True
        reasons.append(f"Channel '{channel}' is not permitted (allowed: {', '.join(r['channels'])}).")
    terr = [t.upper() for t in r.get("territories") or []]
    if territory:
        t = territory.upper()
        if t in [x.upper() for x in r.get("excluded_territories") or []]:
            blocked = True
            reasons.append(f"Territory {t} is excluded.")
        elif terr and "WW" not in terr and t not in terr:
            blocked = True
            reasons.append(f"Territory {t} is not licensed (licensed: {', '.join(terr)}).")
    restricted = status == "restricted"
    if restricted:
        reasons.append("Marked as restricted: check the notes before use.")
    if use in RELEASE_USES and people_visible and r.get("model_release") not in OK_RELEASES:
        restricted = True
        reasons.append(f"People are visible and the model release is '{r.get('model_release')}'.")
    if r.get("brand_safety") == "unsafe":
        restricted = True
        reasons.append("Flagged as not brand safe.")
    verdict = "blocked" if blocked else "restricted" if restricted else "allowed"
    if verdict == "allowed":
        reasons.append("Cleared for this use." if use or channel or territory else "Cleared.")
    return {"verdict": verdict, "reasons": reasons, "rights": r}


def summary_status(r: dict[str, Any], on: str | None = None) -> str:
    """Badge for the UI: cleared | restricted | expiring | expired | not_cleared | unknown."""
    st = r.get("status", "unknown")
    if st in ("unknown", "not_cleared", "restricted"):
        return st
    day = dt.date.fromisoformat(on[:10]) if on else dt.date.today()
    if r.get("expires"):
        exp = dt.date.fromisoformat(r["expires"])
        if exp < day:
            return "expired"
        if (exp - day).days <= 30:
            return "expiring"
    return "cleared"
