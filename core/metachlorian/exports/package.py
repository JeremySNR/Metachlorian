"""Handoff packages for Cutawan and editing software.

Implements docs/integration/cutawan-contract.md (package format v1): a
directory with manifest.json (validated against
docs/integration/cutawan-package.schema.json before it is written), media,
transcripts, timelines (OTIO, FCPXML 1.10, CMX 3600), RIGHTS.md and
checksums. Written to a temporary directory and renamed into place; the
manifest is written last, so a directory with a manifest is complete.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import time
import zipfile
from fractions import Fraction
from pathlib import Path
from typing import Any

from .. import __version__, rights as R
from ..config import Settings
from ..db import Database, loads
from ..media import ffmpeg
from ..records import build_asset_doc, build_shot_doc
from ..vocab import registry
from . import timeline as T

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "integration" / "cutawan-package.schema.json"
_CROCK = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
TAG_FIELDS = {"camera.shot_size": "shot_size", "camera.movement": "camera_movement", "shot.role": "shot_role", "semantic.mood": "mood",
              "content.setting": "setting", "content.time_of_day": "time_of_day", "pacing.pace": "pace", "camera.angle": "camera_angle"}
A_ROLES = {"interview", "piece_to_camera", "a_roll", "vox_pop"}


def ulid() -> str:
    t = int(time.time() * 1000)
    r = int.from_bytes(secrets.token_bytes(10), "big")
    n = (t << 80) | r
    return "".join(_CROCK[(n >> (5 * i)) & 31] for i in reversed(range(26)))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "package"


def schema() -> dict[str, Any] | None:
    for p in (SCHEMA_PATH, Path(os.environ.get("METACHLORIAN_HOME", "")) / "docs/integration/cutawan-package.schema.json"):
        if p.exists():
            return json.loads(p.read_text())
    try:  # installed wheel: bundled copy
        from importlib.resources import files

        return json.loads((files("metachlorian") / "schemas" / "cutawan-package.schema.json").read_text())
    except Exception:
        return None


def validate_manifest(m: dict[str, Any]) -> list[str]:
    import jsonschema

    sch = schema()
    if sch is None:
        return ["package schema not found"]
    v = jsonschema.Draft202012Validator(sch)
    return [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in sorted(v.iter_errors(m), key=lambda e: list(e.path))]


def _time(seconds: float, rate: Fraction, tc_offset: float = 0.0) -> dict[str, Any]:
    seconds = max(0.0, float(seconds))
    return {"seconds": round(seconds, 4), "rate": f"{rate.numerator}/{rate.denominator}", "frames": T.frames(seconds, rate),
            "timecode": T.timecode(seconds + tc_offset, rate)}


def _tags(doc: dict[str, Any], min_conf: float = 0.4) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for field, vocab in TAG_FIELDS.items():
        v = doc["fields"].get(field, {}).get("value")
        items = v if isinstance(v, list) else [v] if isinstance(v, dict) else []
        terms = [i["term"] for i in items if isinstance(i, dict) and i.get("term") and (i.get("confidence") or 0) >= min_conf]
        if terms:
            out[vocab] = list(dict.fromkeys(terms))
    return out


def _scalar(doc: dict[str, Any], field: str) -> Any:
    v = doc["fields"].get(field, {}).get("value")
    return v.get("value", v.get("term")) if isinstance(v, dict) else v


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _words(db: Database, asset_id: int, a: float, b: float) -> list[dict[str, Any]]:
    out = []
    for m in db.q("SELECT data FROM moments WHERE asset_id=? AND kind='speech' AND end_s > ? AND start_s < ? ORDER BY start_s", (asset_id, a, b)):
        for w in (loads(m["data"], {}) or {}).get("words", []):
            mid = (w["s"] + w["e"]) / 2
            if a <= mid < b:
                out.append(w)
    return out


def build_package(db: Database, settings: Settings, items: list[dict[str, Any]], name: str, brief: str = "",
                  target: dict[str, Any] | None = None, media_policy: str = "proxies", mode: str | None = None,
                  timelines: tuple[str, ...] = ("otio", "fcpxml", "edl"), handles: float = 1.0, actor: str = "",
                  out_dir: Path | None = None, zip_it: bool = False, search_echo: dict[str, Any] | None = None) -> dict[str, Any]:
    if not items:
        raise ValueError("a package needs at least one shot")
    if media_policy not in ("none", "proxies", "trimmed_originals", "stringout"):
        raise ValueError("media_policy must be none, proxies, trimmed_originals or stringout")
    target = dict(target or {})
    target.setdefault("consumer", "cutawan")
    target.setdefault("aspect", "original")
    pid = ulid()
    final = (out_dir or settings.export_dir) / f"{slug(name)}-{pid}"
    tmp = final.with_name("." + final.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    for d in ("media", "transcripts", "thumbs", "timelines"):
        (tmp / d).mkdir(parents=True, exist_ok=True)
    reg = registry()
    # ------------------------------------------------------------ resolve shots
    resolved = []
    for n, it in enumerate(items, 1):
        sh = db.q1("SELECT id FROM shots WHERE uid=?", (it["shot_uid"],))
        if not sh:
            raise KeyError(f"unknown shot {it['shot_uid']}")
        doc = build_shot_doc(db, sh["id"])
        a_in = float(it.get("in") if it.get("in") is not None else doc["start"])
        a_out = float(it.get("out") if it.get("out") is not None else doc["end"])
        if not (doc["start"] - 1e-3 <= a_in < a_out <= doc["end"] + 1e-3):
            raise ValueError(f"in/out for {it['shot_uid']} must lie inside the shot ({doc['start']}–{doc['end']} s)")
        roles = [r["term"] for r in (doc["fields"].get("shot.role", {}).get("value") or []) if isinstance(r, dict)]
        role = it.get("role") or (roles[0] if roles else "b_roll")
        resolved.append({"item_id": f"it_{n:02d}", "doc": doc, "in": a_in, "out": a_out, "role": role, "note": it.get("note", "")})
    asset_docs = {r["doc"]["asset_id"]: build_asset_doc(db, r["doc"]["asset_id"]) for r in resolved}
    # ------------------------------------------------------------ rights
    usages = target.get("usage") or [None]
    channels = target.get("channels") or [None]
    territories = target.get("territories") or [None]
    order = {"allowed": 0, "unknown": 1, "restricted": 2, "blocked": 3}
    records: dict[str, Any] = {}
    counts = {"allowed": 0, "restricted": 0, "blocked": 0, "unknown": 0}
    credits: list[str] = []
    earliest: str | None = None
    for r in resolved:
        d = r["doc"]
        override = db.q1("SELECT 1 FROM rights WHERE asset_id=? AND shot_id=?", (d["asset_id"], d["id"]))
        rr = R.get_rights(db, d["asset_id"], d["id"] if override else None)
        worst = {"verdict": "allowed", "reasons": []}
        for u in usages:
            for c in channels:
                for t in territories:
                    chk = R.check(rr, u, c, t if t not in (None, "WORLD") else None, people_visible=bool(_scalar(d, "people.count")))
                    if order[chk["verdict"]] > order[worst["verdict"]]:
                        worst = chk
                    elif chk["verdict"] == worst["verdict"] and chk["verdict"] != "allowed":
                        worst = {**worst, "reasons": list(dict.fromkeys(worst["reasons"] + chk["reasons"]))}
        ref = f"r_{r['item_id']}"
        r["rights_ref"] = ref
        r["verdict"] = worst["verdict"]
        counts[worst["verdict"]] += 1
        rec: dict[str, Any] = {"verdict": worst["verdict"],
                               "reasons": [{"code": _reason_code(x), "detail": x} for x in worst.get("reasons", []) if worst["verdict"] != "allowed"]}
        if rr.get("model_release") in reg.get("release_status").terms:
            rec["model_release"] = rr["model_release"]
        if rr.get("property_release") in reg.get("release_status").terms:
            rec["property_release"] = rr["property_release"]
        if rr.get("licence"):
            rec["licence"] = {"name": rr["licence"]}
        if rr.get("attribution"):
            rec["credit"] = rr["attribution"]
            credits.append(rr["attribution"])
        if rr.get("expires"):
            rec["expires_at"] = rr["expires"]
            earliest = min(earliest or rr["expires"], rr["expires"])
        perm = {k: v for k, v in (("usage", rr.get("permitted_uses")), ("channels", rr.get("channels")),
                                  ("territories", ["WORLD" if x == "WW" else x for x in rr.get("territories") or []])) if v}
        if perm:
            rec["permitted"] = perm
        records[ref] = rec
    verdict = max((r["verdict"] for r in resolved), key=lambda v: order[v])
    # ------------------------------------------------------------ media
    seq_rate = T.rate_of(next(iter(asset_docs.values())).get("fps"))
    media_entries: list[dict[str, Any]] = []
    for r in resolved:
        d = r["doc"]
        a = asset_docs[d["asset_id"]]
        src = Path(a["path"]) if not str(a["path"]).startswith("s3://") else Path(db.q1("SELECT local_path FROM assets WHERE id=?", (a["id"],))["local_path"] or "")
        proxy = settings.media_dir / d["asset_uid"] / "proxy.mp4"
        h_in = max(0.0, r["in"] - handles)
        h_out = min(float(a.get("duration") or r["out"]), r["out"] + handles)
        r["asset_offset"] = h_in
        thumb_src = settings.media_dir / d["asset_uid"] / (d.get("thumb") or "")
        if d.get("thumb") and thumb_src.exists():
            shutil.copy2(thumb_src, tmp / "thumbs" / f"{r['item_id']}.jpg")
        if media_policy in ("proxies", "trimmed_originals", "stringout"):
            fname = f"{r['item_id']}.mp4"
            if media_policy == "trimmed_originals" and src.exists():
                ffmpeg.render_clip(src, tmp / "media" / fname, h_in, h_out, reencode=True)
                kind = "trimmed_original"
            else:
                ffmpeg.render_clip(proxy if proxy.exists() else src, tmp / "media" / fname, h_in, h_out, reencode=True)
                kind = "proxy"
            info = ffmpeg.technical_metadata(tmp / "media" / fname)
            r["media_file"] = f"media/{fname}"
            r["media_duration"] = float(info.get("duration") or (h_out - h_in))
            r["media_in"], r["media_out"] = r["in"] - h_in, r["out"] - h_in
            r["media_w"], r["media_h"] = info.get("width") or 1920, info.get("height") or 1080
            media_entries.append({"file": r["media_file"], "kind": kind, "asset_id": d["asset_uid"], "asset_offset": round(h_in, 4),
                                  "duration": round(r["media_duration"], 4), "rate": _rat(T.rate_of(info.get("fps"))),
                                  "width": r["media_w"], "height": r["media_h"], "video_codec": info.get("video_codec") or "h264",
                                  "audio_codec": info.get("audio_codec") or "aac", "has_audio": bool(info.get("audio_channels")),
                                  "sha256": _sha(tmp / "media" / fname)})
        else:
            r["media_file"] = None
            r["media_duration"] = float(a.get("duration") or 0)
            r["media_in"], r["media_out"] = r["in"], r["out"]
            r["asset_offset"] = 0.0
    # ------------------------------------------------------------ sequence and mode
    a_items = [r for r in resolved if r["role"] in A_ROLES]
    b_items = [r for r in resolved if r["role"] not in A_ROLES]
    if mode is None:
        mode = "a_roll_with_inserts" if a_items and b_items else "stringout"
    if mode == "a_roll_with_inserts" and not a_items:
        raise ValueError("a_roll_with_inserts needs at least one A-roll item (role interview, piece_to_camera, a_roll or vox_pop);"
                         " use stringout or broll_library instead")
    if media_policy == "none" and mode != "broll_library":
        mode = mode if mode in ("stringout", "a_roll_with_inserts") else "stringout"
    clips: list[T.Clip] = []
    width = max((r.get("media_w") or asset_docs[r["doc"]["asset_id"]].get("width") or 1920) for r in resolved)
    height = max((r.get("media_h") or asset_docs[r["doc"]["asset_id"]].get("height") or 1080) for r in resolved)
    main = a_items if mode == "a_roll_with_inserts" else resolved
    cursor = 0.0
    for r in main:
        clips.append(_clip(r, asset_docs, cursor, 1, seq_rate))
        r["record_in"] = cursor
        cursor += r["out"] - r["in"]
    inserts = []
    if mode == "a_roll_with_inserts":
        total = cursor
        # Spread inserts evenly over the A-roll, never past its end, one at a time.
        slot = total / (len(b_items) + 1) if b_items else 0
        for k, r in enumerate(b_items, 1):
            dur = min(r["out"] - r["in"], max(1.0, slot * 0.9))
            start = max(0.0, min(total - dur, slot * k - dur / 2))
            r["out"] = r["in"] + dur
            if r.get("media_file"):
                r["media_out"] = r["media_in"] + dur
            clips.append(_clip(r, asset_docs, start, 2, seq_rate))
            r["record_in"] = start
            inserts.append({"item_id": r["item_id"], "start": round(start, 3), "end": round(start + dur, 3), "mode": "fullscreen"})
    seq = T.Sequence(name=name, rate=seq_rate, width=width, height=height, clips=clips)
    # ------------------------------------------------------------ stringout + transcript
    stringout = None
    transcripts = []
    if media_policy != "none" and mode in ("stringout", "a_roll_with_inserts"):
        parts = [r for r in main if r.get("media_file")]
        if parts:
            so_name = "stringout_a_roll.mp4" if mode == "a_roll_with_inserts" else "stringout.mp4"
            _concat(tmp, [(tmp / r["media_file"], r["media_in"], r["media_out"]) for r in parts], tmp / "media" / so_name, seq_rate, width, height)
            info = ffmpeg.technical_metadata(tmp / "media" / so_name)
            media_entries.append({"file": f"media/{so_name}", "kind": "stringout", "duration": round(float(info.get("duration") or cursor), 4),
                                  "rate": _rat(seq_rate), "width": info.get("width") or width, "height": info.get("height") or height,
                                  "video_codec": "h264", "audio_codec": "aac", "has_audio": True, "sha256": _sha(tmp / "media" / so_name)})
            segs, words_all = [], []
            pos = 0.0
            for r in parts:
                ws = _words(db, r["doc"]["asset_id"], r["in"], r["out"])
                seg_words = [{"text": w["w"], "start": round(pos + w["s"] - r["in"], 3), "end": round(pos + w["e"] - r["in"], 3)} for w in ws]
                if seg_words:
                    segs.append({"id": len(segs), "text": " ".join(w["text"] for w in seg_words), "start": seg_words[0]["start"],
                                 "end": seg_words[-1]["end"], "words": seg_words})
                    words_all += seg_words
                pos += r["out"] - r["in"]
            lang = None
            for r in parts:
                la = db.q1("SELECT value FROM signals WHERE asset_id=? AND name='audio.language' AND level='asset'", (r["doc"]["asset_id"],))
                if la:
                    lang = (loads(la["value"]) or {}).get("code")
                    break
            tr_name = so_name.replace(".mp4", ".json")
            (tmp / "transcripts" / tr_name).write_text(json.dumps({"language": lang or "und", "durationSec": round(pos, 3), "segments": segs},
                                                                  ensure_ascii=False, indent=1))
            transcripts.append({"file": f"transcripts/{tr_name}", "format": "cutawan.transcript/1", "time_base": "media",
                                "media_file": f"media/{so_name}", **({"language": lang} if lang else {})})
            stringout = {"sequence_id": "seq_main", "file": f"media/{so_name}", "scope": "a_roll" if mode == "a_roll_with_inserts" else "all",
                         "transcript": f"transcripts/{tr_name}",
                         "map": [{"item_id": r["item_id"], "in": round(r["record_in"], 4), "out": round(r["record_in"] + r["out"] - r["in"], 4)} for r in parts]}
    # ------------------------------------------------------------ timelines
    tl_entries = []
    rel = lambda p: f"../{p}" if p else ""  # noqa: E731  timelines live one level down
    tl_seq = T.Sequence(seq.name, seq.rate, seq.width, seq.height,
                        [T.Clip(**{**c.__dict__, "media_path": rel(c.media_path) if not os.path.isabs(c.media_path) else c.media_path}) for c in seq.clips])
    media_paths = "relative" if media_policy != "none" else "absolute"
    if "otio" in timelines:
        T.write_otio(tl_seq, tmp / "timelines" / "seq_main.otio")
        tl_entries.append({"format": "otio", "version": "Timeline.1", "file": "timelines/seq_main.otio", "sequence_id": "seq_main", "media_paths": media_paths})
    if "fcpxml" in timelines:
        T.write_fcpxml(tl_seq, tmp / "timelines" / "seq_main.fcpxml")
        tl_entries.append({"format": "fcpxml", "version": "1.10", "file": "timelines/seq_main.fcpxml", "sequence_id": "seq_main", "media_paths": media_paths})
    if "edl" in timelines:
        T.write_edl(seq, tmp / "timelines" / "seq_main.edl")
        tl_entries.append({"format": "edl_cmx3600", "file": "timelines/seq_main.edl", "sequence_id": "seq_main", "media_paths": "missing"})
    # ------------------------------------------------------------ manifest
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    m_items = []
    for r in resolved:
        d = r["doc"]
        rate = T.rate_of(asset_docs[d["asset_id"]].get("fps"))
        tc0 = _tc_offset(asset_docs[d["asset_id"]])
        item: dict[str, Any] = {"item_id": r["item_id"], "shot_id": d["uid"], "asset_id": d["asset_uid"], "role": r["role"],
                                "source_range": {"in": _time(r["in"], rate, tc0), "out": _time(r["out"], rate, tc0)},
                                "rights_ref": r["rights_ref"]}
        if handles and r.get("media_file"):
            item["handles_sec"] = handles
        if r.get("media_file"):
            item["media"] = {"file": r["media_file"], "in": round(r["media_in"], 4), "out": round(r["media_out"], 4)}
        desc = _scalar(d, "content.summary") or _scalar(d, "content.caption")
        if desc:
            item["description"] = str(desc)[:1000]
        tags = _tags(d)
        if tags:
            item["tags"] = tags
        ws = _words(db, d["asset_id"], r["in"], r["out"])
        if ws:
            item["transcript_excerpt"] = {"text": " ".join(w["w"] for w in ws)[:2000]}
        vc = _scalar(d, "composition.vertical_crop")
        if isinstance(vc, dict) and vc.get("width"):
            x = max(0.0, min(1 - vc["width"], vc["x_centre"] - vc["width"] / 2))
            item["safe_crops"] = {"9:16": {"rect": {"x": round(x, 4), "y": 0.0, "width": round(vc["width"], 4), "height": 1.0}}}
        m_items.append(_prune(item, "item"))
    m_assets = []
    for aid, a in asset_docs.items():
        t = a.get("technical", {})
        ent = {"asset_id": a["uid"], "name": a["filename"], "original_filename": a["filename"], "duration": round(float(a.get("duration") or 0), 4),
               "rate": _rat(T.rate_of(a.get("fps"))), "width": a.get("width") or 0, "height": a.get("height") or 0,
               "has_audio": bool(t.get("audio_channels")), "original_uri": Path(a["path"]).as_uri() if os.path.isabs(a["path"]) else a["path"]}
        et = a.get("edit_type")
        et = et.get("term") if isinstance(et, dict) else et
        if et:
            ent["edit_type"] = et
        if t.get("timecode"):
            ent["start_timecode"] = t["timecode"]
        m_assets.append(_prune(ent, "asset"))
    sequences = [{"sequence_id": "seq_main", "name": name, "rate": _rat(seq_rate), "width": width, "height": height,
                  "duration": round(seq.duration, 4),
                  "tracks": [t for t in (
                      {"name": "V1", "kind": "video", "role": "a_roll" if mode == "a_roll_with_inserts" else "b_roll",
                       "clips": [{"item_id": r["item_id"], "record_in": round(r["record_in"], 4), "duration": round(r["out"] - r["in"], 4)} for r in main]},
                      {"name": "V2", "kind": "video", "role": "b_roll",
                       "clips": [{"item_id": r["item_id"], "record_in": round(r["record_in"], 4), "duration": round(r["out"] - r["in"], 4)} for r in b_items]}
                      if mode == "a_roll_with_inserts" and b_items else None,
                      {"name": "A1", "kind": "audio", "role": "a_roll" if mode == "a_roll_with_inserts" else "b_roll",
                       "clips": [{"item_id": r["item_id"], "record_in": round(r["record_in"], 4), "duration": round(r["out"] - r["in"], 4)} for r in main]})
                      if t]}]
    rights_human = _rights_md(name, resolved, records, verdict, target)
    (tmp / "RIGHTS.md").write_text(rights_human)
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0", "kind": "metachlorian.package", "package_id": pid, "name": name, "created_at": now_iso,
        "generator": {"name": "metachlorian", "version": __version__},
        "brief": _prune({"text": brief, "search": search_echo} if search_echo else {"text": brief}, "brief"),
        "target": _prune({k: v for k, v in target.items() if k in ("consumer", "aspect", "duration_sec", "usage", "channels", "territories")}, "target"),
        "vocab_versions": {v: reg.get(v).version for v in sorted({v for it in m_items for v in it.get("tags", {})} | {"shot_role"})},
        "media_policy": media_policy, "assets": m_assets, "media": media_entries, "items": m_items, "sequences": sequences,
        "transcripts": transcripts, "timelines": tl_entries,
        "rights": _prune({"verdict": verdict, "intended": _prune({"usage": [u for u in usages if u], "channels": [c for c in channels if c],
                                                                    "territories": [t for t in territories if t]}, "x"),
                          "counts": counts, "checked_at": now_iso, "credits": sorted(set(credits)), "earliest_expiry": earliest,
                          "records": records, "human_readable": "RIGHTS.md"}, "rights"),
    }
    if stringout:
        manifest["stringout"] = stringout
    if target.get("consumer") == "cutawan":
        aspect = target.get("aspect") if target.get("aspect") in ("9:16", "1:1", "16:9") else "9:16"
        manifest["cutawan"] = _prune({"mode": mode, "project_name": name, "flow": "whole-video" if mode != "broll_library" else None,
                                      "aspect": aspect, "captions": True, "auto_zoom": mode == "a_roll_with_inserts",
                                      "inserts": inserts or None}, "cutawan")
    manifest = _prune(manifest, "root")
    errors = validate_manifest(manifest)
    if errors:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError("package manifest failed schema validation: " + "; ".join(errors[:8]))
    sums = []
    for p in sorted(tmp.rglob("*")):
        if p.is_file() and p.name not in ("checksums.sha256", "manifest.json"):
            sums.append(f"{_sha(p)}  {p.relative_to(tmp).as_posix()}")
    (tmp / "checksums.sha256").write_text("\n".join(sums) + "\n")
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    os.replace(tmp, final)
    result: dict[str, Any] = {"package_id": pid, "path": str(final), "manifest": manifest, "verdict": verdict, "counts": counts}
    if zip_it:
        zpath = final.with_suffix(".zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(final.rglob("*")):
                if p.is_file():
                    z.write(p, f"{final.name}/{p.relative_to(final).as_posix()}")
        result["zip"] = str(zpath)
    return result


def _rat(r: Fraction) -> str:
    return f"{r.numerator}/{r.denominator}"


def _tc_offset(a: dict[str, Any]) -> float:
    tc = (a.get("technical") or {}).get("timecode")
    if not tc:
        return 0.0
    try:
        h, m, s, f = [int(x) for x in re.split(r"[:;.]", tc)]
        return h * 3600 + m * 60 + s + f / max(1.0, float(a.get("fps") or 25))
    except ValueError:
        return 0.0


def _clip(r: dict[str, Any], asset_docs, record_in: float, track: int, rate: Fraction) -> T.Clip:
    a = asset_docs[r["doc"]["asset_id"]]
    path = r["media_file"] or a["path"]
    return T.Clip(name=f"{a['filename']} #{r['doc']['idx'] + 1}", reel=Path(a["filename"]).stem[:8], media_path=path,
                  media_duration=r["media_duration"], src_in=r["media_in"], src_out=r["media_out"], record_in=record_in, track=track,
                  has_audio=bool((a.get("technical") or {}).get("audio_channels")), asset_offset=r.get("asset_offset", 0.0) + _tc_offset(a),
                  asset_rate=rate, note=(r["note"] or str(_scalar(r["doc"], "content.caption") or ""))[:200])


def _concat(tmp: Path, parts: list[tuple[Path, float, float]], out: Path, rate: Fraction, w: int, h: int) -> None:
    """Frame-accurate conform of trimmed parts into one CFR H.264/AAC file."""
    args = [ffmpeg.ffmpeg_bin(), "-y", "-v", "error"]
    for p, a, b in parts:
        args += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(p)]
    fc = []
    for i in range(len(parts)):
        fc.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={rate.numerator}/{rate.denominator}[v{i}]")
        fc.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}]")
    fc.append("".join(f"[v{i}][a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=1[v][a]")
    args += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-g", str(max(1, round(float(rate)))), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    try:
        ffmpeg.run(args)
    except RuntimeError:
        # Parts without audio: add silent audio and retry.
        fixed = []
        for i, (p, a, b) in enumerate(parts):
            q = tmp / f".part{i}.mp4"
            ffmpeg.run([ffmpeg.ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(p), "-f", "lavfi",
                        "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a", "-shortest", "-c:v", "libx264", "-preset", "fast",
                        "-crf", "18", "-c:a", "aac", str(q)])
            fixed.append((q, 0.0, b - a))
        _concat(tmp, fixed, out, rate, w, h)
        for q, _, _ in fixed:
            q.unlink(missing_ok=True)


def _reason_code(text: str) -> str:
    t = text.lower()
    for key, code in (("expired", "licence_expired"), ("starts on", "licence_not_started"), ("channel", "channel_not_permitted"),
                      ("territory", "territory_not_permitted"), ("use '", "usage_not_permitted"), ("model release", "release_unknown"),
                      ("not cleared", "not_cleared"), ("restricted", "restricted"), ("brand safe", "brand_safety"),
                      ("no rights information", "rights_unknown")):
        if key in t:
            return code
    return "other"


def _rights_md(name, resolved, records, verdict, target) -> str:
    lines = [f"# Rights summary: {name}", "", f"Overall verdict: **{verdict}**", ""]
    if target.get("usage") or target.get("channels") or target.get("territories"):
        lines.append(f"Checked for use {', '.join(target.get('usage') or ['any'])}, channels {', '.join(target.get('channels') or ['any'])}, "
                     f"territories {', '.join(target.get('territories') or ['any'])}.")
        lines.append("")
    lines += ["| Item | Shot | Verdict | Notes |", "|---|---|---|---|"]
    for r in resolved:
        rec = records[r["rights_ref"]]
        notes = "; ".join(x["detail"] for x in rec.get("reasons", [])) or rec.get("credit", "")
        lines.append(f"| {r['item_id']} | {r['doc']['filename']} {r['in']:.2f}–{r['out']:.2f} s | {rec['verdict']} | {notes} |")
    lines += ["", "Generated by Metachlorian. Rights are as recorded at build time; check before publishing."]
    return "\n".join(lines) + "\n"


def _prune(d: dict[str, Any], _ctx: str) -> dict[str, Any]:
    """Drop None / empty values (the schema forbids nulls in most places)."""
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {} and v != ""}


def export_clip(db: Database, settings: Settings, shot_uid: str, a_in: float | None = None, a_out: float | None = None,
                mode: str = "proxy", out_dir: Path | None = None) -> dict[str, Any]:
    """One clip as a file (from original or proxy), a reference, or a one-clip timeline."""
    sh = db.q1("SELECT id FROM shots WHERE uid=?", (shot_uid,))
    if not sh:
        raise KeyError(shot_uid)
    doc = build_shot_doc(db, sh["id"])
    a = build_asset_doc(db, doc["asset_id"])
    a_in = doc["start"] if a_in is None else float(a_in)
    a_out = doc["end"] if a_out is None else float(a_out)
    if not (0 <= a_in < a_out <= float(a.get("duration") or a_out) + 1e-3):
        raise ValueError("in/out out of range")
    rate = T.rate_of(a.get("fps"))
    ref = {"shot_uid": shot_uid, "asset_uid": a["uid"], "path": a["path"], "in": round(a_in, 4), "out": round(a_out, 4),
           "in_timecode": T.timecode(a_in + _tc_offset(a), rate), "out_timecode": T.timecode(a_out + _tc_offset(a), rate),
           "rate": _rat(rate), "in_frame": T.frames(a_in, rate), "out_frame": T.frames(a_out, rate)}
    if mode == "reference":
        return {"mode": mode, "reference": ref}
    out_dir = out_dir or settings.export_dir / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(a['filename']).stem}_{T.timecode(a_in, rate).replace(':', '').replace(';', '')}-{T.timecode(a_out, rate).replace(':', '').replace(';', '')}"
    if mode in ("file", "proxy"):
        src = Path(a["path"]) if mode == "file" else settings.media_dir / a["uid"] / "proxy.mp4"
        if mode == "file" and not src.exists():
            raise FileNotFoundError("the original file is not reachable from this server; use mode=proxy")
        dst = out_dir / f"{stem}{'_proxy' if mode == 'proxy' else ''}.mp4"
        ffmpeg.render_clip(src, dst, a_in, a_out, reencode=True)
        return {"mode": mode, "file": str(dst), "bytes": dst.stat().st_size, "reference": ref}
    if mode in ("otio", "fcpxml", "edl"):
        seq = T.Sequence(stem, rate, a.get("width") or 1920, a.get("height") or 1080, [T.Clip(
            name=stem, reel=Path(a["filename"]).stem[:8], media_path=a["path"], media_duration=float(a.get("duration") or a_out),
            src_in=a_in, src_out=a_out, record_in=0.0, has_audio=bool((a.get("technical") or {}).get("audio_channels")),
            asset_offset=_tc_offset(a))])
        dst = out_dir / f"{stem}.{ {'otio': 'otio', 'fcpxml': 'fcpxml', 'edl': 'edl'}[mode] }"
        {"otio": T.write_otio, "fcpxml": T.write_fcpxml, "edl": T.write_edl}[mode](seq, dst)
        return {"mode": mode, "file": str(dst), "reference": ref}
    raise ValueError("mode must be reference, proxy, file, otio, fcpxml or edl")
