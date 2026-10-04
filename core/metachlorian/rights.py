"""Rights and clearance.

Rights are recorded per asset and can be overridden per shot. A use check
returns one of: allowed, restricted (needs a human decision), blocked, or
unknown (nothing recorded). Search with an intended use returns only
``allowed`` shots unless the caller explicitly asks for more.
"""
from __future__ import annotations

import datetime as dt
import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .db import Database, dumps, loads, now
from .vocab import registry

if TYPE_CHECKING:
    from .auth import Principal

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
    if st in ("unknown", "not_cleared"):
        return st
    day = dt.date.fromisoformat(on[:10]) if on else dt.date.today()
    if r.get("expires"):
        exp = dt.date.fromisoformat(r["expires"])
        if exp < day:
            return "expired"  # a restricted licence that has run out is expired, not merely restricted
        if st == "cleared" and (exp - day).days <= 30:
            return "expiring"
    return st if st == "restricted" else "cleared"


# ---------------------------------------------------------------------- the gate
# Every exit that can hand out a shot (search and similar results, clip exports, packages, proxy
# media) asks ``gate`` whether it may, so the rules live in one place and are tested once.
BLOCKED_BADGES = frozenset({"not_cleared", "expired"})  # blocked for every use: never leaves as media
VERDICT_ORDER = {"allowed": 0, "unknown": 1, "restricted": 2, "blocked": 3}
MODES = ("list", "reference", "media", "package")


@dataclass(frozen=True)
class Verdict:
    verdict: str              # allowed | restricted | blocked | unknown, for the intended use (or for any use)
    reasons: tuple[str, ...]
    badge: str                # summary_status: cleared | restricted | expiring | expired | not_cleared | unknown
    permitted: bool           # may this principal do this with the shot
    refusal: str = ""         # why not, when not permitted

    @property
    def blocked(self) -> bool:
        return self.badge in BLOCKED_BADGES

    def as_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "reasons": list(self.reasons)}


def _as_list(v: Any) -> list[Any]:
    if v is None or v == "" or v == []:
        return [None]
    return list(v) if isinstance(v, (list, tuple)) else [v]


def check_all(r: dict[str, Any], intended: dict[str, Any] | None = None, people_visible: bool = False) -> dict[str, Any]:
    """The worst verdict over every use x channel x territory combination of an intended use (each
    may be a single value or a list), with the reasons of every combination that reached it."""
    intended = intended or {}
    worst: dict[str, Any] | None = None
    for u, c, t in itertools.product(_as_list(intended.get("use")), _as_list(intended.get("channel")), _as_list(intended.get("territory"))):
        chk = check(r, u, c, t, intended.get("date"), people_visible=people_visible)
        if worst is None or VERDICT_ORDER[chk["verdict"]] > VERDICT_ORDER[worst["verdict"]]:
            worst = chk
        elif chk["verdict"] == worst["verdict"] and chk["verdict"] != "allowed":
            worst = {**worst, "reasons": list(dict.fromkeys(worst["reasons"] + chk["reasons"]))}
    assert worst is not None
    return worst


def gate(r: dict[str, Any], *, principal: "Principal | None" = None, mode: str = "list", intended: dict[str, Any] | None = None,
         people_visible: bool = False, include: list[str] | tuple[str, ...] | None = None, hide_blocked: bool = True,
         allow_restricted: bool = False) -> Verdict:
    """May ``principal`` take this shot out through ``mode``?

    ``r`` is the shot's rights (``get_rights`` with its shot id, so an override wins). Modes:

    * ``list`` (search and similar results): blocked footage is hidden unless ``hide_blocked`` is off;
      with an intended use only verdicts in ``include`` (default: allowed) are listed. Same for everyone.
    * ``reference`` (paths and timecodes, no media): always permitted.
    * ``media`` (proxy, original or timeline exports): blocked footage never leaves, for anyone; an agent
      also needs an ``allowed`` verdict for the intended use (no intended use: the rights as recorded).
    * ``package`` (hand-off packages): as ``media``, except that ``allow_restricted`` lets an agent
      through with restricted or unknown items (never blocked ones).
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    try:
        badge = summary_status(r)
        chk = check_all(r, intended, people_visible)
        verdict, reasons = chk["verdict"], tuple(chk["reasons"])
    except ValueError:  # a malformed date written outside set_rights: fail closed
        badge, verdict, reasons = "not_cleared", "blocked", ("The rights record has an invalid date.",)
    agent = principal is not None and principal.is_agent
    refusal = ""
    if mode == "list":
        if hide_blocked and badge in BLOCKED_BADGES:
            refusal = "blocked footage is hidden"
        elif intended and verdict not in set(include or ["allowed"]):
            refusal = f"rights verdict is '{verdict}'"
    elif mode in ("media", "package"):
        if badge in BLOCKED_BADGES:
            refusal = ("this shot is blocked (" + ("not cleared" if badge == "not_cleared" else "rights expired")
                       + "); change its rights before exporting media")
        elif agent and verdict != "allowed" and not (mode == "package" and allow_restricted and verdict != "blocked"):
            refusal = f"rights verdict is '{verdict}': {'; '.join(reasons)}"
    return Verdict(verdict, reasons, badge, not refusal, refusal)
