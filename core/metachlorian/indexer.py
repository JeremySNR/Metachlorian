"""Write effective shot records into the query structures: typed filter
columns (shot_index), faceted terms (shot_terms) and full text (shot_fts).
Vectors live in the ``vectors`` table and are mirrored into the in-memory ANN
index by the search service."""
from __future__ import annotations

from typing import Any

from .config import Settings
from .db import Database, dumps, now
from .records import FREE_TERM_FIELDS, VOCAB_FIELDS, build_shot_docs, scalar, term_list
from .vocab import registry


def _f(doc: dict[str, Any], name: str) -> Any:
    f = doc["fields"].get(name)
    return f["value"] if f else None


def index_asset(db: Database, settings: Settings | None, asset_id: int) -> int:
    a = db.q1("SELECT id, deleted_at FROM assets WHERE id=?", (asset_id,))
    if not a:
        return 0
    docs = build_shot_docs(db, asset_id) if not a["deleted_at"] else []
    reg = registry()
    with db.tx() as c:
        old = [r[0] for r in c.execute("SELECT shot_id FROM shot_index WHERE asset_id=?", (asset_id,)).fetchall()]
        if old:
            q = ",".join("?" * len(old))
            c.execute(f"DELETE FROM shot_terms WHERE shot_id IN ({q})", old)
            c.execute(f"DELETE FROM shot_fts WHERE rowid IN ({q})", old)
            c.execute(f"DELETE FROM shot_index WHERE shot_id IN ({q})", old)
        for d in docs:
            t = d["technical"]
            w, h = t.get("width") or 0, t.get("height") or 0
            people = scalar(_f(d, "people.count"))
            classes = {x["term"] for x in term_list(_f(d, "audio.classes")) if (x.get("confidence") or 0) >= 0.3}
            moves = term_list(_f(d, "camera.movement"))
            roles = term_list(_f(d, "shot.role"))
            caption = scalar(_f(d, "content.caption")) or ""
            summary = scalar(_f(d, "content.summary")) or ""
            usable = scalar(_f(d, "quality.usable"))
            edit = (d.get("edit_type") or {}).get("term") if isinstance(d.get("edit_type"), dict) else d.get("edit_type")
            loc = scalar(_f(d, "content.location")) or scalar(_f(d, "content.location_guess")) or ""
            c.execute(
                "INSERT INTO shot_index(shot_id, asset_id, duration, start_s, end_s, width, height, fps, aspect, log_profile, hdr, people_count,"
                " faces, speech, music, motion_energy, pace, shot_size, camera_movement, role, time_of_day, usable, quality, capture_date,"
                " location, edit_type, caption, doc, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d["id"], asset_id, d["duration"], d["start"], d["end"], w, h, t.get("fps"), (w / h) if h else None,
                 int(bool(t.get("log_profile"))), int(bool(t.get("hdr"))), people if isinstance(people, int) else None,
                 _f(d, "people.faces"), int("speech" in classes), int("music" in classes or "singing" in classes),
                 _f(d, "pacing.motion_energy"), scalar(_f(d, "pacing.pace")), scalar(_f(d, "camera.shot_size")),
                 moves[0]["term"] if moves else None, roles[0]["term"] if roles else None, scalar(_f(d, "content.time_of_day")),
                 None if usable is None else int(bool(usable)), scalar(_f(d, "quality.score")), str(t.get("capture_date") or "") or None,
                 loc or None, edit, caption, dumps(d), now()))
            terms: dict[tuple[str, str], tuple[float, str]] = {}
            for field, (vocab, _) in VOCAB_FIELDS.items():
                fld = d["fields"].get(field)
                if not fld:
                    continue
                for x in term_list(fld["value"]):
                    src = "human" if fld.get("corrected") else ",".join(x.get("sources", [fld["source"]])) if isinstance(x, dict) else fld["source"]
                    terms[(vocab, x["term"])] = (float(x.get("confidence") or 0.5), src)
            for field, vocab in FREE_TERM_FIELDS.items():
                fld = d["fields"].get(field)
                if not fld:
                    continue
                for x in term_list(fld["value"]):
                    terms[(vocab, str(x["term"]).lower()[:60])] = (float(x.get("confidence") or 0.5), fld["source"])
            for tag in term_list(_f(d, "tags")):
                terms[("tag", str(tag["term"]).lower())] = (1.0, "human")
            if edit:
                terms[("edit_type", edit)] = (1.0, "rollup")
            if t.get("resolution_class"):
                terms[("resolution", t["resolution_class"])] = (1.0, "technical")
            if t.get("orientation"):
                terms[("orientation", t["orientation"])] = (1.0, "technical")
            if t.get("log_profile"):
                terms[("look", "log")] = (float(t.get("log_confidence") or 0.6), "quality")
            if t.get("hdr"):
                terms[("look", "hdr")] = (1.0, "technical")
            c.executemany("INSERT OR REPLACE INTO shot_terms(shot_id, vocab, term, confidence, source) VALUES(?,?,?,?,?)",
                          [(d["id"], v, tm, cf, src) for (v, tm), (cf, src) in terms.items()])
            # Full text: labels and synonyms make vocabulary words findable by keyword too.
            tag_words = []
            for (v, tm), (cf, _) in terms.items():
                if cf < 0.3:
                    continue
                if v in reg.vocabs and tm in reg.get(v).terms:
                    tag_words.append(reg.get(v).terms[tm].label)
                else:
                    tag_words.append(tm.replace("_", " "))
            transcript = scalar(_f(d, "audio.transcript")) or ""
            ocr = scalar(_f(d, "content.ocr_text")) or ""
            logos = scalar(_f(d, "content.logos_text")) or []
            fn = d["filename"].rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
            path_words = " ".join(p for p in d["path"].replace("\\", "/").split("/")[-4:-1])
            c.execute("INSERT INTO shot_fts(rowid, caption, transcript, ocr, tags, place, filename) VALUES(?,?,?,?,?,?,?)",
                      (d["id"], f"{caption} {summary}", transcript, f"{ocr} {' '.join(logos) if isinstance(logos, list) else logos}",
                       " ".join(tag_words), f"{loc} {path_words}", fn))
    return len(docs)


def reindex_all(db: Database, settings: Settings | None = None) -> int:
    n = 0
    for r in db.q("SELECT id FROM assets"):
        n += index_asset(db, settings, r["id"])
    return n
