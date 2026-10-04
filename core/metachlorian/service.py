"""The library service: every operation the app, the REST API and the MCP
server offer, with permission checks and audit logging in one place, so
agents are never second-class users and never get more than people do."""
from __future__ import annotations

import posixpath
import shutil
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__, rights as R
from .auth import Forbidden, Principal, audit, require
from .config import Settings
from .db import Database, dumps, loads, now
from .exports import package as P
from .indexer import index_asset
from .ingest.scan import add_source, register_file, scan_source
from .jobs import queue
from .records import ASSET_CORRECTABLE, CORRECTABLE, build_asset_doc, build_shot_doc, collect, record_correction, revert_correction
from .search.engine import SearchEngine, SearchRequest, summarise_doc
from .vocab import registry


def _timecode(t: float, fps: float | None) -> str:
    """HH:MM:SS:FF at the file's nominal rate (non-drop), for display."""
    rate = round(fps) if fps else 25
    frames = int(round(t * (fps or rate)))
    ff = frames % rate
    secs = frames // rate
    return f"{secs // 3600:02d}:{secs // 60 % 60:02d}:{secs % 60:02d}:{ff:02d}"


class NotFound(Exception):
    pass


class Library:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.engine = SearchEngine(db, settings)
        self._lock = threading.Lock()
        registry().load_custom(db)

    # ------------------------------------------------------------------ helpers
    def _log(self, p: Principal, action: str, target: str = "", detail: dict[str, Any] | None = None, write: bool = False) -> None:
        # Writes are always audited; reads are audited for agents.
        if write or p.is_agent:
            audit(self.db, p, action, target, detail)

    def _shot_id(self, uid: str) -> int:
        r = self.db.q1("SELECT id FROM shots WHERE uid=?", (uid,))
        if not r:
            raise NotFound(f"no shot {uid}")
        return r["id"]

    def _asset_row(self, uid: str):
        r = self.db.q1("SELECT * FROM assets WHERE uid=?", (uid,))
        if not r:
            raise NotFound(f"no asset {uid}")
        return r

    def _shot_rights(self, doc: dict[str, Any]) -> dict[str, Any]:
        r = R.get_rights(self.db, doc["asset_id"], doc["id"])  # the shot's override when it has one, else the asset's
        return {**r, "badge": R.summary_status(r)}

    def media_access(self, p: Principal, asset_uid: str) -> None:
        """Proxy, sprites, posters and keyframes under /media/<asset>/. People with library:read see them
        all (reviewing footage is how rights get fixed); agents get nothing from a file holding any blocked
        shot, because those files cover the whole asset."""
        require(p, "library:read")
        if not p.is_agent:
            return
        a = self.db.q1("SELECT id FROM assets WHERE uid=?", (asset_uid,))
        if not a:
            return  # nothing to protect; the route answers 404
        rows = self.db.q("SELECT shot_id FROM rights WHERE asset_id=?", (a["id"],))
        for r in [{"shot_id": None}] + [dict(x) for x in rows if x["shot_id"] is not None]:
            if R.summary_status(R.get_rights(self.db, a["id"], r["shot_id"])) in R.BLOCKED_BADGES:
                raise Forbidden("this file holds blocked footage (not cleared or rights expired); agents cannot fetch its media")

    # ------------------------------------------------------------------ read
    def health(self) -> dict[str, Any]:
        from . import models

        return {"name": "metachlorian", "version": __version__, "auth_required": self.settings.require_auth,
                "egress": self.settings.egress_summary(), "vlm": bool(self.settings.vlm.enabled), "llm": bool(self.settings.llm.enabled),
                "models": {m["name"]: m["installed"] for m in models.status(self.settings.resolved_models_dir)}}

    def search(self, p: Principal, req: SearchRequest | dict[str, Any]) -> dict[str, Any]:
        require(p, "library:read")
        if isinstance(req, dict):
            req = SearchRequest.from_dict(req)
        if p.is_agent and req.intended_use is None:
            pass  # agents may search without a use; check_rights / build_package enforce clearance
        out = self.engine.search(req)
        self._log(p, "search_shots", req.q[:200], {"filters": req.filters, "intended_use": req.intended_use, "results": len(out["results"])})
        return out

    def get_shot(self, p: Principal, uid: str, intended: dict[str, Any] | None = None) -> dict[str, Any]:
        require(p, "library:read")
        doc = build_shot_doc(self.db, self._shot_id(uid))
        doc["rights"] = self._shot_rights(doc)
        if intended:
            doc["rights_check"] = R.check(doc["rights"], intended.get("use"), intended.get("channel"), intended.get("territory"),
                                          intended.get("date"), people_visible=bool(summarise_doc(doc).get("people")))
        words = []
        for m in self.db.q("SELECT start_s, end_s, text, data FROM moments WHERE shot_id=? AND kind='speech' ORDER BY start_s", (doc["id"],)):
            d = loads(m["data"], {}) or {}
            words.append({"start": m["start_s"], "end": m["end_s"], "text": m["text"], "speaker": d.get("speaker"), "words": d.get("words", [])})
        doc["transcript"] = words
        a = self.db.q1("SELECT uid FROM assets WHERE id=?", (doc["asset_id"],))
        doc["media"] = {"proxy": f"/media/{a['uid']}/proxy.mp4", "sprites": f"/media/{a['uid']}/sprites/",
                        "poster": f"/media/{a['uid']}/{doc['poster']}" if doc.get("poster") else None,
                        "thumb": f"/media/{a['uid']}/{doc['thumb']}" if doc.get("thumb") else None}
        neighbours = self.db.q("SELECT uid, idx FROM shots WHERE asset_id=? AND active=1 AND idx IN (?, ?)", (doc["asset_id"], doc["idx"] - 1, doc["idx"] + 1))
        doc["neighbours"] = {("previous" if r["idx"] < doc["idx"] else "next"): r["uid"] for r in neighbours}
        doc["summary"] = summarise_doc(doc)
        # Every folder the file was found in (duplicates live in several).
        doc["folders"] = sorted({posixpath.dirname(r["path"].replace("\\", "/"))
                                 for r in self.db.q("SELECT path FROM asset_paths WHERE asset_id=?", (doc["asset_id"],))})
        self._log(p, "get_shot", uid)
        return doc

    def get_asset(self, p: Principal, uid: str) -> dict[str, Any]:
        require(p, "library:read")
        a = self._asset_row(uid)
        doc = build_asset_doc(self.db, a["id"])
        rows = self.db.q("SELECT doc FROM shot_index WHERE asset_id=? ORDER BY start_s", (a["id"],))
        doc["shots"] = [summarise_doc(loads(r["doc"])) for r in rows]
        if not doc["shots"]:
            doc["shots"] = [{"uid": s["uid"], "idx": s["idx"], "start": s["start_s"], "end": s["end_s"], "duration": s["end_s"] - s["start_s"]}
                            for s in self.db.q("SELECT * FROM shots WHERE asset_id=? AND active=1 ORDER BY idx", (a["id"],))]
        doc["rights"] = {**R.get_rights(self.db, a["id"]), "badge": R.summary_status(R.get_rights(self.db, a["id"]))}
        doc["processing"] = [dict(r) for r in self.db.q("SELECT analyser, version, status, error, seconds, finished_at FROM analysis_runs WHERE asset_id=? ORDER BY id", (a["id"],))]
        doc["jobs"] = [dict(r) for r in self.db.q("SELECT analyser, status, attempts, error FROM jobs WHERE asset_id=? AND status IN ('queued','running','failed')", (a["id"],))]
        sp = self.db.q1("SELECT output FROM analysis_runs WHERE asset_id=? AND analyser='proxy' AND status='done'", (a["id"],))
        out = loads(sp["output"], {}) if sp else {}
        doc["media"] = {"proxy": f"/media/{uid}/proxy.mp4" if out else None, "poster": f"/media/{uid}/poster.jpg" if out else None,
                        "sprites": {**out.get("sprites", {}), "base": f"/media/{uid}/sprites/"} if out.get("sprites") else None}
        transcript = self.db.q("SELECT start_s, end_s, text, data FROM moments WHERE asset_id=? AND kind='speech' ORDER BY start_s", (a["id"],))
        doc["transcript"] = [{"start": t["start_s"], "end": t["end_s"], "text": t["text"], "speaker": (loads(t["data"], {}) or {}).get("speaker")}
                             for t in transcript]
        doc["paths"] = [r["path"] for r in self.db.q("SELECT path FROM asset_paths WHERE asset_id=?", (a["id"],))]
        self._log(p, "get_asset", uid)
        return doc

    def folders(self, p: Principal, q: str = "", parent: str | None = None, limit: int = 500) -> dict[str, Any]:
        require(p, "library:read")
        from .folders import list_folders

        out = list_folders(self.db, q, parent, max(1, min(5000, limit)))
        self._log(p, "list_folders", q)
        return out

    def list_assets(self, p: Principal, q: str = "", edit_type: str | None = None, status: str | None = None, limit: int = 200,
                    offset: int = 0, folder: str | None = None, collection: str | None = None) -> dict[str, Any]:
        require(p, "library:read")
        where, args = ["deleted_at IS NULL"], []
        if folder:
            from .folders import like_pattern

            where.append("id IN (SELECT asset_id FROM asset_paths WHERE replace(path, '\\', '/') LIKE ? ESCAPE '\\')")
            args.append(like_pattern(folder))
        if collection:
            where.append("id IN (SELECT s.asset_id FROM collection_items i JOIN shots s ON s.id=i.shot_id JOIN collections c ON c.id=i.collection_id"
                         " WHERE c.uid=? OR lower(c.name)=lower(?))")
            args += [collection, collection]
        if q:
            where.append("(filename LIKE ? OR path LIKE ? OR summary LIKE ?)")
            args += [f"%{q}%"] * 3
        if status:
            where.append("status=?")
            args.append(status)
        if edit_type:
            where.append("json_extract(summary, '$.edit_type.term') = ?")
            args.append(edit_type)
        total = self.db.q1(f"SELECT COUNT(*) n FROM assets WHERE {' AND '.join(where)}", args)["n"]
        rows = self.db.q(f"SELECT * FROM assets WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*args, limit, offset))
        out = []
        for r in rows:
            s = loads(r["summary"], {}) or {}
            rr = R.get_rights(self.db, r["id"])
            tech = loads(r["tech"], {}) or {}
            out.append({"uid": r["uid"], "filename": r["filename"], "path": r["path"], "status": r["status"], "duration": r["duration"],
                        "captured": tech.get("capture_date"),
                        "width": r["width"], "height": r["height"], "fps": r["fps"], "size": r["size"], "created_at": r["created_at"],
                        "edit_type": s.get("edit_type"), "shot_count": s.get("shot_count"), "cuts_per_minute": s.get("cuts_per_minute"),
                        "summary": (s.get("summary") or {}).get("story") or (s.get("summary") or {}).get("text"),
                        "poster": f"/media/{r['uid']}/poster.jpg", "rights_badge": R.summary_status(rr), "pace": s.get("pace"),
                        "topics": s.get("topics", [])})
        self._log(p, "list_assets", q)
        return {"total": total, "assets": out}

    def find_similar(self, p: Principal, shot_uid: str | None = None, image: bytes | None = None, clip: Path | None = None,
                     limit: int = 24, intended: dict[str, Any] | None = None, filters: dict[str, Any] | None = None,
                     modality: str = "visual", hide_blocked: bool = True) -> dict[str, Any]:
        require(p, "library:read")
        req = SearchRequest(limit=limit, intended_use=intended, filters=filters or {}, similar_space=modality, hide_blocked=hide_blocked)
        if shot_uid:
            self._shot_id(shot_uid)
            req.similar_to = shot_uid
        elif image is not None or clip is not None:
            from .media import ffmpeg, siglip

            enc = siglip.load(str(self.settings.resolved_models_dir))
            if image is not None:
                import cv2

                img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    raise ValueError("could not decode the image")
                v = enc.encode_images([cv2.cvtColor(img, cv2.COLOR_BGR2RGB)])[0]
            else:
                dur = float(ffmpeg.ffprobe(clip)["format"].get("duration") or 1)
                frames = ffmpeg.frames_at(clip, [dur * f for f in (0.2, 0.5, 0.8)], 512)
                v = enc.encode_images(frames).mean(axis=0)
            req.vector = (v / (np.linalg.norm(v) + 1e-9)).tolist()
        else:
            raise ValueError("give a shot, an image or a clip")
        out = self.engine.search(req)
        self._log(p, "find_similar", shot_uid or ("image" if image else "clip"), {"results": len(out["results"])})
        return out

    # ------------------------------------------------------------------ people (face identity, local only)
    def people(self, p: Principal, q: str = "", named: bool | None = None, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        require(p, "library:read")
        from . import people as PP

        out = PP.list_people(self.db, q, named, max(1, min(500, limit)), max(0, offset))
        out["enabled"] = self.settings.face_identity
        self._log(p, "list_people", q)
        return out

    def person(self, p: Principal, identity_id: int, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        require(p, "library:read")
        from . import people as PP

        row = self.db.q1("SELECT id, name, named_by FROM identities WHERE id=?", (identity_id,))
        if not row:
            raise NotFound(f"no person {identity_id}")
        faces = PP.person_faces(self.db, identity_id, limit, offset)
        shots = sorted({f["shot_uid"] for f in faces})
        self._log(p, "get_person", str(identity_id))
        return {"id": row["id"], "name": row["name"], "label": row["name"] or f"Person {row['id']}", "named_by": row["named_by"],
                "faces": faces, "shot_uids": shots}

    def _people_write(self, p: Principal) -> None:
        require(p, "tags:write")
        if p.is_agent:
            raise Forbidden("naming and grouping people is a decision for a person, not an agent")

    def _reindex(self, asset_ids: list[int]) -> None:
        for aid in dict.fromkeys(asset_ids):
            index_asset(self.db, self.settings, aid)

    def rename_person(self, p: Principal, identity_id: int, name: str) -> dict[str, Any]:
        self._people_write(p)
        from . import people as PP

        try:
            PP.rename(self.db, identity_id, name, p.username)
        except KeyError as e:
            raise NotFound(f"no person {identity_id}") from e
        self._reindex(PP.assets_of(self.db, [identity_id]))
        self._log(p, "rename_person", str(identity_id), {"name": name}, write=True)
        return self.person(p, identity_id, limit=24)

    def merge_people(self, p: Principal, source_id: int, into_id: int) -> dict[str, Any]:
        self._people_write(p)
        from . import people as PP

        try:
            PP.merge(self.db, source_id, into_id)
        except KeyError as e:
            raise NotFound(f"no person {e}") from e
        self._reindex(PP.assets_of(self.db, [into_id]))
        self._log(p, "merge_people", str(source_id), {"into": into_id}, write=True)
        return self.person(p, into_id, limit=24)

    def move_face(self, p: Principal, face_id: int, identity_id: int | None) -> dict[str, Any]:
        self._people_write(p)
        from . import people as PP

        row = self.db.q1("SELECT asset_id FROM faces WHERE id=?", (face_id,))
        if not row:
            raise NotFound(f"no face {face_id}")
        try:
            target = PP.move_face(self.db, face_id, identity_id)
        except KeyError as e:
            raise NotFound(f"no person {e}") from e
        self._reindex([row["asset_id"]])
        self._log(p, "move_face", str(face_id), {"to": identity_id, "new_person": identity_id is None}, write=True)
        return {"face_id": face_id, "identity_id": target}

    def forget_person(self, p: Principal, identity_id: int) -> dict[str, Any]:
        require(p, "admin")
        from . import people as PP

        try:
            affected, thumbs = PP.forget(self.db, identity_id)
        except KeyError as e:
            raise NotFound(f"no person {identity_id}") from e
        for t in thumbs:
            (self.settings.media_dir / t).unlink(missing_ok=True)
        self._reindex(affected)
        self._log(p, "forget_person", str(identity_id), {"faces_deleted": len(thumbs)}, write=True)
        return {"forgotten": identity_id, "faces_deleted": len(thumbs)}

    def check_rights(self, p: Principal, shot_uids: list[str] | None = None, asset_uids: list[str] | None = None, use: str | None = None,
                     channel: str | None = None, territory: str | None = None, date: str | None = None) -> dict[str, Any]:
        require(p, "library:read")
        out = []
        for uid in shot_uids or []:
            doc = build_shot_doc(self.db, self._shot_id(uid))
            rr = self._shot_rights(doc)
            res = R.check(rr, use, channel, territory, date, people_visible=bool(summarise_doc(doc).get("people")))
            out.append({"shot_uid": uid, "verdict": res["verdict"], "reasons": res["reasons"], "rights": {k: v for k, v in rr.items() if k != "notes"}})
        for uid in asset_uids or []:
            a = self._asset_row(uid)
            rr = R.get_rights(self.db, a["id"])
            res = R.check(rr, use, channel, territory, date)
            out.append({"asset_uid": uid, "verdict": res["verdict"], "reasons": res["reasons"], "rights": rr})
        order = {"allowed": 0, "unknown": 1, "restricted": 2, "blocked": 3}
        overall = max((o["verdict"] for o in out), key=lambda v: order[v], default="unknown")
        self._log(p, "check_rights", ",".join((shot_uids or []) + (asset_uids or []))[:200], {"use": use, "channel": channel, "territory": territory})
        return {"verdict": overall, "items": out}

    def library_stats(self, p: Principal) -> dict[str, Any]:
        require(p, "library:read")
        reg = registry()
        a = self.db.q1("SELECT COUNT(*) n, SUM(duration) d, SUM(size) s FROM assets WHERE deleted_at IS NULL")
        shots = self.db.q1("SELECT COUNT(*) n FROM shot_index")["n"]
        status = {r["status"]: r["n"] for r in self.db.q("SELECT status, COUNT(*) n FROM assets WHERE deleted_at IS NULL GROUP BY status")}
        edit = Counter()
        topics = Counter()
        places = Counter()
        for r in self.db.q("SELECT summary FROM assets WHERE deleted_at IS NULL"):
            s = loads(r["summary"], {}) or {}
            if s.get("edit_type"):
                edit[s["edit_type"]["term"]] += 1
            topics.update(s.get("topics", []))
            places.update(s.get("locations", []))
        facets: dict[str, list[dict[str, Any]]] = {}
        for vocab in ("shot_size", "camera_movement", "shot_role", "setting", "time_of_day", "weather", "season", "pace", "mood", "audio_class"):
            counts = {r["term"]: r["n"] for r in self.db.q("SELECT term, COUNT(*) n FROM shot_terms WHERE vocab=? AND confidence >= 0.4 GROUP BY term", (vocab,))}
            v = reg.get(vocab)
            facets[vocab] = [{"term": t.id, "label": t.label, "count": counts.get(t.id, 0)} for t in v.terms.values() if not t.broader or counts.get(t.id)]
        # Coverage gaps: top-level terms with no confident shots.
        gaps = []
        for vocab in ("setting", "time_of_day", "weather", "season", "shot_size", "shot_role"):
            for item in facets.get(vocab, []):
                if item["count"] == 0:
                    gaps.append({"vocab": vocab, "term": item["term"], "label": item["label"]})
        rights = Counter()
        for r in self.db.q("SELECT a.id FROM assets a WHERE a.deleted_at IS NULL"):
            rights[R.summary_status(R.get_rights(self.db, r["id"]))] += 1
        self._log(p, "library_stats")
        return {"assets": a["n"], "hours": round((a["d"] or 0) / 3600, 3), "bytes": a["s"] or 0, "shots": shots, "status": status,
                "edit_types": dict(edit), "topics": topics.most_common(30), "places": places.most_common(30), "facets": facets,
                "gaps": gaps, "rights": dict(rights), "jobs": queue.stats(self.db)["by_status"], "throughput": queue.throughput(self.db)}

    def vocabularies(self, p: Principal, name: str | None = None) -> dict[str, Any]:
        require(p, "library:read")
        reg = registry()
        if name:
            return reg.get(name).as_dict()
        return {"version": reg.version, "vocabularies": {n: {"version": v.version, "description": v.description, "multi": v.multi,
                                                             "terms": len(v.terms)} for n, v in reg.vocabs.items()}}

    # ------------------------------------------------------------------ corrections
    def correct(self, p: Principal, field: str, op: str, value: Any, shot_uid: str | None = None, asset_uid: str | None = None,
                note: str = "") -> dict[str, Any]:
        require(p, "tags:write")
        if shot_uid:
            sid = self._shot_id(shot_uid)
            a = self.db.q1("SELECT a.uid, a.id FROM shots s JOIN assets a ON a.id=s.asset_id WHERE s.id=?", (sid,))
            cid = record_correction(self.db, "shot", a["uid"], field, op, value, p.username, p.user_id, shot_uid, note)
        elif asset_uid:
            a = self._asset_row(asset_uid)
            cid = record_correction(self.db, "asset", asset_uid, field, op, value, p.username, p.user_id, None, note)
        else:
            raise ValueError("give shot_uid or asset_uid")
        index_asset(self.db, self.settings, a["id"])
        self._log(p, "correct_tag", shot_uid or asset_uid or "", {"field": field, "op": op, "value": value, "note": note, "id": cid}, write=True)
        return {"correction_id": cid, "record": self.get_shot(p, shot_uid) if shot_uid else self.get_asset(p, asset_uid or "")}

    def corrections(self, p: Principal, asset_uid: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        require(p, "library:read")
        if asset_uid:
            rows = self.db.q("SELECT * FROM corrections WHERE asset_uid=? ORDER BY id DESC LIMIT ?", (asset_uid, limit))
        else:
            rows = self.db.q("SELECT c.*, a.filename FROM corrections c LEFT JOIN assets a ON a.uid=c.asset_uid ORDER BY c.id DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            d = {**dict(r), "value": loads(r["value"])}
            # Where it applies and what the model says there, so the log reads "Night -> Morning" on "Shot 3 at 00:00:08".
            sh = self.db.q1("SELECT id, idx, start_s, end_s FROM shots WHERE uid=?", (r["shot_uid"],)) if r["shot_uid"] else None
            if sh:
                fps = (self.db.q1("SELECT fps FROM assets WHERE uid=?", (r["asset_uid"],)) or {"fps": None})["fps"]
                d["shot"] = {"idx": sh["idx"], "number": sh["idx"] + 1, "start": sh["start_s"], "end": sh["end_s"], "fps": fps,
                             "timecode": _timecode(sh["start_s"], fps)}
                m = collect(self.db, "shot", sh["id"]).get(r["field"])
                d["model_value"] = {"value": m["value"], "source": m["source"], "confidence": m["confidence"]} if m else None
            else:
                d["shot"] = {"start": r["anchor_start"], "end": r["anchor_end"]} if r["anchor_start"] is not None else None
                d["model_value"] = None
            out.append(d)
        return out

    def revert(self, p: Principal, correction_id: int) -> None:
        require(p, "tags:write")
        r = self.db.q1("SELECT asset_uid FROM corrections WHERE id=?", (correction_id,))
        if not r:
            raise NotFound("no such correction")
        revert_correction(self.db, correction_id)
        a = self._asset_row(r["asset_uid"])
        index_asset(self.db, self.settings, a["id"])
        self._log(p, "revert_correction", str(correction_id), write=True)

    def correctable(self) -> dict[str, Any]:
        return {"shot": CORRECTABLE, "asset": ASSET_CORRECTABLE}

    # ------------------------------------------------------------------ rights
    def get_rights(self, p: Principal, asset_uid: str, shot_uid: str | None = None) -> dict[str, Any]:
        require(p, "library:read")
        a = self._asset_row(asset_uid)
        r = R.get_rights(self.db, a["id"], self._shot_id(shot_uid) if shot_uid else None)
        return {**r, "badge": R.summary_status(r)}

    def set_rights(self, p: Principal, asset_uid: str, data: dict[str, Any], shot_uid: str | None = None) -> dict[str, Any]:
        require(p, "rights:write")
        if p.is_agent:
            raise Forbidden("agents cannot change rights")
        a = self._asset_row(asset_uid)
        r = R.set_rights(self.db, a["id"], data, p.username, self._shot_id(shot_uid) if shot_uid else None)
        index_asset(self.db, self.settings, a["id"])
        self._log(p, "set_rights", shot_uid or asset_uid, data, write=True)
        return {**r, "badge": R.summary_status(r)}

    def bulk_rights(self, p: Principal, asset_uids: list[str], data: dict[str, Any]) -> int:
        for u in asset_uids:
            self.set_rights(p, u, data)
        return len(asset_uids)

    # ------------------------------------------------------------------ collections
    def collections(self, p: Principal) -> list[dict[str, Any]]:
        require(p, "library:read")
        rows = self.db.q("SELECT c.*, (SELECT COUNT(*) FROM collection_items i WHERE i.collection_id=c.id) n,"
                         " (SELECT SUM(IFNULL(i.out_s, s.end_s) - IFNULL(i.in_s, s.start_s)) FROM collection_items i JOIN shots s ON s.id=i.shot_id WHERE i.collection_id=c.id) d"
                         " FROM collections c ORDER BY c.updated_at DESC")
        return [{"uid": r["uid"], "name": r["name"], "description": r["description"], "kind": r["kind"], "brief": r["brief"], "owner": r["owner"],
                 "items": r["n"], "duration": round(r["d"] or 0, 2), "updated_at": r["updated_at"]} for r in rows]

    def collection(self, p: Principal, uid: str) -> dict[str, Any]:
        require(p, "library:read")
        c = self.db.q1("SELECT * FROM collections WHERE uid=?", (uid,))
        if not c:
            raise NotFound(f"no collection {uid}")
        items = []
        for r in self.db.q("SELECT i.*, s.uid suid, s.asset_id FROM collection_items i JOIN shots s ON s.id=i.shot_id WHERE i.collection_id=? ORDER BY i.position", (c["id"],)):
            d = self.db.q1("SELECT doc FROM shot_index WHERE shot_id=?", (r["shot_id"],))
            summ = summarise_doc(loads(d["doc"])) if d else {"uid": r["suid"]}
            rr = R.get_rights(self.db, r["asset_id"], r["shot_id"])
            items.append({"item_id": r["id"], "position": r["position"], "in": r["in_s"], "out": r["out_s"], "note": r["note"],
                          "shot": summ, "rights_badge": R.summary_status(rr)})
        return {"uid": c["uid"], "name": c["name"], "description": c["description"], "kind": c["kind"], "brief": c["brief"],
                "owner": c["owner"], "items": items, "created_at": c["created_at"], "updated_at": c["updated_at"]}

    def create_collection(self, p: Principal, name: str, description: str = "", kind: str = "collection", brief: str = "") -> dict[str, Any]:
        require(p, "collections:write")
        from .ingest.scan import new_uid

        uid = new_uid("c")
        self.db.x("INSERT INTO collections(uid, name, description, kind, brief, owner, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (uid, name.strip() or "Untitled", description, kind, brief, p.username, now(), now()))
        self._log(p, "create_collection", uid, {"name": name}, write=True)
        return self.collection(p, uid)

    def update_collection(self, p: Principal, uid: str, **fields: Any) -> dict[str, Any]:
        require(p, "collections:write")
        allowed = {k: v for k, v in fields.items() if k in ("name", "description", "kind", "brief") and v is not None}
        if allowed:
            self.db.x(f"UPDATE collections SET {', '.join(f'{k}=?' for k in allowed)}, updated_at=? WHERE uid=?", (*allowed.values(), now(), uid))
        self._log(p, "update_collection", uid, allowed, write=True)
        return self.collection(p, uid)

    def delete_collection(self, p: Principal, uid: str) -> None:
        require(p, "collections:write")
        self.db.x("DELETE FROM collections WHERE uid=?", (uid,))
        self._log(p, "delete_collection", uid, write=True)

    def add_to_collection(self, p: Principal, uid: str, shot_uids: list[str], in_s: float | None = None, out_s: float | None = None,
                          note: str = "") -> dict[str, Any]:
        require(p, "collections:write")
        c = self.db.q1("SELECT id FROM collections WHERE uid=?", (uid,))
        if not c:
            raise NotFound(f"no collection {uid}")
        pos = (self.db.q1("SELECT MAX(position) m FROM collection_items WHERE collection_id=?", (c["id"],))["m"] or 0)
        for su in shot_uids:
            pos += 1
            self.db.x("INSERT INTO collection_items(collection_id, shot_id, position, in_s, out_s, note, added_by, added_at) VALUES(?,?,?,?,?,?,?,?)",
                      (c["id"], self._shot_id(su), pos, in_s, out_s, note, p.username, now()))
        self.db.x("UPDATE collections SET updated_at=? WHERE id=?", (now(), c["id"]))
        self._log(p, "add_to_collection", uid, {"shots": shot_uids}, write=True)
        return self.collection(p, uid)

    def update_item(self, p: Principal, uid: str, item_id: int, **fields: Any) -> dict[str, Any]:
        require(p, "collections:write")
        allowed = {{"in": "in_s", "out": "out_s"}.get(k, k): v for k, v in fields.items() if k in ("in", "out", "note", "position")}
        if allowed:
            self.db.x(f"UPDATE collection_items SET {', '.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), item_id))
        return self.collection(p, uid)

    def reorder(self, p: Principal, uid: str, item_ids: list[int]) -> dict[str, Any]:
        require(p, "collections:write")
        with self.db.tx() as c:
            for i, iid in enumerate(item_ids, 1):
                c.execute("UPDATE collection_items SET position=? WHERE id=?", (i, iid))
        return self.collection(p, uid)

    def remove_item(self, p: Principal, uid: str, item_id: int) -> dict[str, Any]:
        require(p, "collections:write")
        self.db.x("DELETE FROM collection_items WHERE id=?", (item_id,))
        self._log(p, "remove_from_collection", uid, {"item": item_id}, write=True)
        return self.collection(p, uid)

    # ------------------------------------------------------------------ exports
    def export_clip(self, p: Principal, shot_uid: str, in_s: float | None = None, out_s: float | None = None, mode: str = "proxy",
                    intended: dict[str, Any] | None = None) -> dict[str, Any]:
        require(p, "media:export")
        # Blocked footage never leaves as media, for people or agents; agents also need an 'allowed' verdict.
        doc = build_shot_doc(self.db, self._shot_id(shot_uid))
        v = R.gate(self._shot_rights(doc), principal=p, mode="reference" if mode == "reference" else "media",
                   intended={k: (intended or {}).get(k) for k in ("use", "channel", "territory", "date")},
                   people_visible=bool(summarise_doc(doc).get("people")))
        if not v.permitted:
            self._log(p, "export_clip", shot_uid, {"refused": v.verdict, "badge": v.badge, "mode": mode}, write=True)
            raise Forbidden(v.refusal)
        res = P.export_clip(self.db, self.settings, shot_uid, in_s, out_s, mode)
        if res.get("file"):
            res["download"] = "/api/exports/file?path=" + str(Path(res["file"]).relative_to(self.settings.export_dir))
        self._log(p, "export_clip", shot_uid, {"mode": mode, "in": in_s, "out": out_s}, write=True)
        return res

    def build_package(self, p: Principal, items: list[dict[str, Any]] | None = None, collection_uid: str | None = None, name: str = "",
                      brief: str = "", target: dict[str, Any] | None = None, media_policy: str = "proxies", mode: str | None = None,
                      allow_restricted: bool = False, zip_it: bool = False) -> dict[str, Any]:
        require(p, "media:export")
        if collection_uid:
            c = self.collection(p, collection_uid)
            items = [{"shot_uid": i["shot"]["uid"], "in": i["in"], "out": i["out"], "note": i["note"]} for i in c["items"]]
            name = name or c["name"]
            brief = brief or c["brief"]
        if not items:
            raise ValueError("no shots to package")
        try:
            # The package checks every item through rights.gate before it renders anything.
            res = P.build_package(self.db, self.settings, items, name or "Metachlorian package", brief, target, media_policy, mode,
                                  actor=p.username, zip_it=zip_it, principal=p, allow_restricted=allow_restricted)
        except P.Refused as e:
            self._log(p, "build_package", name, {"refused": e.verdict, "counts": e.counts}, write=True)
            raise
        res["download"] = "/api/exports/file?path=" + Path(res["path"]).name
        res.pop("manifest_obj", None)
        self._log(p, "build_package", name, {"items": len(items), "verdict": res["verdict"], "path": res["path"]}, write=True)
        return res

    # ------------------------------------------------------------------ ingest
    def sources(self, p: Principal) -> list[dict[str, Any]]:
        require(p, "library:read")
        out = []
        for r in self.db.q("SELECT s.*, (SELECT COUNT(*) FROM assets a WHERE a.source_id=s.id AND a.deleted_at IS NULL) n FROM sources s ORDER BY s.id"):
            out.append({**dict(r), "options": loads(r["options"], {}), "assets": r["n"]})
        return out

    def add_source(self, p: Principal, uri: str, watch: bool = True, scan: bool = True) -> dict[str, Any]:
        require(p, "ingest:write")
        if not uri.startswith("s3://") and not Path(uri).expanduser().exists():
            raise ValueError(f"{uri} does not exist on the server")
        sid = add_source(self.db, uri, watch)
        res = self.scan(p, sid) if scan else {}
        self._log(p, "add_source", uri, write=True)
        return {"id": sid, "scan": res}

    def remove_source(self, p: Principal, source_id: int) -> None:
        require(p, "ingest:write")
        self.db.x("DELETE FROM sources WHERE id=?", (source_id,))
        self._log(p, "remove_source", str(source_id), write=True)

    def scan(self, p: Principal, source_id: int) -> dict[str, Any]:
        require(p, "ingest:write")
        from .pipeline import plan_asset

        res = scan_source(self.db, source_id, self.settings.data_dir / "cache" / "s3")
        for aid in res.asset_ids or []:
            plan_asset(self.db, self.settings, aid)
        return res.as_dict()

    def upload(self, p: Principal, filename: str, stream, priority: int = 5) -> dict[str, Any]:
        require(p, "ingest:write")
        from .ingest.scan import VIDEO_EXTS
        from .pipeline import plan_asset

        safe = Path(filename).name
        if Path(safe).suffix.lower() not in VIDEO_EXTS:
            raise ValueError("unsupported file type")
        dest_dir = self.settings.data_dir / "uploads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / safe
        i = 1
        while dest.exists():
            dest = dest_dir / f"{Path(safe).stem}-{i}{Path(safe).suffix}"
            i += 1
        with dest.open("wb") as f:
            shutil.copyfileobj(stream, f, 1 << 20)
        src = self.db.q1("SELECT id FROM sources WHERE uri=?", (str(dest_dir.resolve()),))
        sid = src["id"] if src else add_source(self.db, str(dest_dir), watch=False, priority=priority)
        outcome, aid = register_file(self.db, dest, sid, priority)
        if aid:
            # New uploads jump the queue.
            self.db.x("UPDATE assets SET priority=? WHERE id=?", (priority, aid))
            plan_asset(self.db, self.settings, aid)
        self._log(p, "upload", safe, {"outcome": outcome}, write=True)
        return {"outcome": outcome, "asset_uid": self.db.q1("SELECT uid FROM assets WHERE id=?", (aid,))["uid"] if aid else None}

    def reprocess(self, p: Principal, asset_uid: str, analysers: list[str] | None = None, priority: int | None = None) -> dict[str, Any]:
        require(p, "ingest:write")
        from .pipeline import plan_asset

        a = self._asset_row(asset_uid)
        with self.db.tx() as c:
            if analysers:
                q = ",".join("?" * len(analysers))
                c.execute(f"DELETE FROM analysis_runs WHERE asset_id=? AND analyser IN ({q})", (a["id"], *analysers))
                c.execute(f"DELETE FROM jobs WHERE asset_id=? AND analyser IN ({q}) AND status NOT IN ('running')", (a["id"], *analysers))
            else:
                c.execute("DELETE FROM analysis_runs WHERE asset_id=? AND status IN ('failed','unavailable')", (a["id"],))
                c.execute("DELETE FROM jobs WHERE asset_id=? AND status IN ('failed','done','cancelled')", (a["id"],))
            if priority is not None:
                c.execute("UPDATE assets SET priority=? WHERE id=?", (priority, a["id"]))
        n = plan_asset(self.db, self.settings, a["id"])
        self._log(p, "reprocess", asset_uid, {"analysers": analysers}, write=True)
        return {"enqueued": n}

    def delete_asset(self, p: Principal, asset_uid: str) -> None:
        require(p, "admin")
        a = self._asset_row(asset_uid)
        self.db.x("UPDATE assets SET deleted_at=? WHERE id=?", (now(), a["id"]))
        self.db.x("DELETE FROM jobs WHERE asset_id=? AND status='queued'", (a["id"],))
        index_asset(self.db, self.settings, a["id"])
        self.db.x("DELETE FROM vectors WHERE asset_id=?", (a["id"],))
        self._log(p, "delete_asset", asset_uid, write=True)

    def processing(self, p: Principal) -> dict[str, Any]:
        require(p, "library:read")
        st = queue.stats(self.db)
        active = [dict(r) for r in self.db.q(
            "SELECT a.uid, a.filename, a.status, a.duration, a.priority, a.updated_at,"
            " (SELECT COUNT(*) FROM jobs j WHERE j.asset_id=a.id AND j.status='queued') queued,"
            " (SELECT COUNT(*) FROM jobs j WHERE j.asset_id=a.id AND j.status='running') running,"
            " (SELECT COUNT(*) FROM analysis_runs r WHERE r.asset_id=a.id AND r.status='done') done,"
            " (SELECT COUNT(*) FROM analysis_runs r WHERE r.asset_id=a.id AND r.status='failed') failed,"
            " (SELECT COUNT(*) FROM analysis_runs r WHERE r.asset_id=a.id AND r.status='unavailable') unavailable"
            " FROM assets a WHERE a.deleted_at IS NULL ORDER BY (a.status IN ('processing','updating')) DESC, a.updated_at DESC LIMIT 200")]
        pending: dict[str, list[str]] = {}
        for r in self.db.q("SELECT a.uid, j.analyser FROM jobs j JOIN assets a ON a.id=j.asset_id WHERE j.status IN ('queued','running')"
                           " ORDER BY j.priority DESC, j.id"):
            pending.setdefault(r["uid"], []).append(r["analyser"])
        for a in active:
            a["pending"] = pending.get(a["uid"], [])
        from .analysers import registry as ar

        analysers = [{"name": a.name, "version": a.version, "description": a.description, "requires": list(a.requires),
                      "available": a.check(self.settings) is None, "reason": a.check(self.settings)} for a in ar.topological()]
        return {"queue": st, "assets": active, "analysers": analysers, "throughput": queue.throughput(self.db)}

    def retry_failed(self, p: Principal) -> int:
        require(p, "ingest:write")
        from .pipeline import plan_all

        self.db.x("DELETE FROM analysis_runs WHERE status='failed'")
        self.db.x("UPDATE jobs SET status='queued', attempts=0, run_after=0, error=NULL WHERE status='failed'")
        n = plan_all(self.db, self.settings)
        self._log(p, "retry_failed", write=True)
        return n

    # ------------------------------------------------------------------ vocab / admin
    def add_term(self, p: Principal, vocab: str, term: str, label: str, definition: str = "", synonyms: list[str] | None = None,
                 broader: str | None = None) -> dict[str, Any]:
        require(p, "admin")
        reg = registry()
        if vocab not in reg.vocabs:
            raise NotFound(f"no vocabulary {vocab}")
        import re

        if not re.fullmatch(r"x_[a-z0-9]+_[a-z0-9_]+", term):
            raise ValueError("local terms must use the x_<org>_<name> id pattern (see vocab README)")
        if broader and broader not in reg.get(vocab).terms:
            raise ValueError(f"broader term {broader} does not exist")
        self.db.x("INSERT OR REPLACE INTO vocab_terms(vocab, term, label, definition, synonyms, broader, created_by, created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (vocab, term, label, definition, dumps(synonyms or []), broader, p.username, now()))
        reg.load_custom(self.db)
        from .search import parse as parse_mod

        parse_mod._PM = None
        self._log(p, "add_term", f"{vocab}:{term}", write=True)
        return reg.get(vocab).terms[term].as_dict()

    def audit_log(self, p: Principal, limit: int = 200, actor: str | None = None, agents_only: bool = False) -> list[dict[str, Any]]:
        require(p, "admin")
        where, args = [], []
        if actor:
            where.append("actor=?")
            args.append(actor)
        if agents_only:
            where.append("role='agent'")
        sql = "SELECT * FROM audit_log" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY id DESC LIMIT ?"
        return [{**dict(r), "detail": loads(r["detail"], {})} for r in self.db.q(sql, (*args, limit))]


_ = dumps
