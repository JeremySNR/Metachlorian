"""Durable contribution queue for newly downloaded YouTube videos.

Sharing is independent of hosted model settings. Rebuild the allowlisted payload at send time; do not queue private
library records. A changed local file, opt-out or deletion prevents a contribution. Visibility is not verified;
the import UI warns users to turn sharing off before importing private or unlisted videos.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..db import Database, loads, now
from ..records import scalar
from .protocol import Contribution, FIELDS, Signal, youtube_url, validate_endpoint

log = logging.getLogger(__name__)
SOURCES = {"fusion", "rollup", "speech", "ocr", "motion", "audio", "quality", "visual_tags"}


class Ineligible(ValueError):
    pass


def enroll(db: Database, settings: Settings, asset_id: int, site: str, info: dict) -> None:
    """Called only for new downloaded bytes, never for local duplicates or scanned files. No historical backfill."""
    if not settings.community_enabled or site.lower() != "youtube":
        return
    video_id = info.get("id") or ""
    try:
        youtube_url(video_id)
    except ValueError:
        return
    a = db.q1("SELECT content_hash FROM assets WHERE id=?", (asset_id,))
    if a and a["content_hash"]:
        db.x("INSERT OR IGNORE INTO community_outbox(asset_id, video_id, imported_hash, updated_at) VALUES(?,?,?,?)",
             (asset_id, video_id, a["content_hash"], now()))


def _fields(db: Database, asset_id: int, level: str, target_id: int) -> dict:
    best = {}
    for r in db.q("SELECT * FROM signals WHERE asset_id=? AND level=? AND target_id=? ORDER BY confidence, id",
                  (asset_id, level, target_id)):
        if r["name"] not in FIELDS or r["source"] not in SOURCES:
            continue
        value = scalar(loads(r["value"]))
        if isinstance(value, list):
            # Wire allowlist: at most 30 terms per field (protocol.Fields).
            value = [v.get("term") if isinstance(v, dict) else v for v in value][:30]
        # Strict validation rejects arbitrary nested dictionaries, local references and raw model responses.
        try:
            signal = Signal(value=value, source=r["source"], confidence=r["confidence"], model_version=r["model_version"])
        except ValidationError:
            continue
        old = best.get(r["name"])
        if old is None or (r["source"] == "fusion" or old["source"] != "fusion"):
            best[r["name"]] = signal.model_dump()
    return best


def build_contribution(db: Database, asset_id: int) -> Contribution | None:
    """The outbox membership is the eligibility boundary; neither filenames nor guessed URLs qualify a file."""
    # Eligibility and machine signals must belong to the same snapshot during concurrent re-analysis.
    with db.tx():
        job = db.q1("SELECT * FROM community_outbox WHERE asset_id=? AND status != 'suppressed'", (asset_id,))
        a = db.q1("SELECT * FROM assets WHERE id=?", (asset_id,))
        if not job or not a or a["deleted_at"] or a["status"] != "ready" or a["content_hash"] != job["imported_hash"]:
            return None
        if db.q1("SELECT 1 FROM jobs WHERE asset_id=? AND status IN ('queued','running') LIMIT 1", (asset_id,)):
            return None
        shots = [{"start_s": r["start_s"], "end_s": r["end_s"], "fields": _fields(db, asset_id, "shot", r["id"])}
                 for r in db.q("SELECT * FROM shots WHERE asset_id=? AND active=1 ORDER BY idx", (asset_id,))][:2000]
        moments = [{k: r[k] for k in ("kind", "start_s", "end_s", "text", "source", "model_version")}
                   for r in db.q("SELECT * FROM moments WHERE asset_id=? AND ((kind='speech' AND source='speech') OR"
                                 " (kind='text' AND source='ocr')) ORDER BY start_s", (asset_id,))][:4000]
        if not shots or not any(s["fields"] for s in shots):
            return None
        from ..ingest.importer import origin_for_asset

        origin = origin_for_asset(db, asset_id) or {}
        try:
            return Contribution(video_id=job["video_id"], title=str(origin.get("title") or "YouTube video")[:500],
                                channel=str(origin.get("uploader") or "")[:300], license=str(origin.get("license") or "")[:500],
                                duration=float(a["duration"]) if a["duration"] and 0 < a["duration"] <= 604800 else None,
                                fields=_fields(db, asset_id, "asset", asset_id), shots=shots, moments=moments)
        except ValidationError as exc:
            # Remaining wire failures are permanent; do not treat them as a transient outage.
            raise Ineligible("Analysis is outside the community contribution allowlist") from exc


def suppress_pending(db: Database) -> None:
    db.x("UPDATE community_outbox SET status='suppressed', message='Sharing was turned off', updated_at=? WHERE status != 'suppressed'",
         (now(),))


def sync_once(db: Database, settings: Settings, transport: httpx.BaseTransport | None = None) -> int:
    """Bounded batch; analysis never waits for this. Retries survive a process restart."""
    if not settings.community_enabled:
        suppress_pending(db)
        return 0
    if not settings.community_url:
        return 0
    endpoint = validate_endpoint(settings.community_url)
    sent = 0
    candidates = db.q("SELECT o.* FROM community_outbox o JOIN assets a ON a.id=o.asset_id WHERE o.status != 'suppressed'"
                      " AND o.run_after<=? AND a.status='ready' AND a.deleted_at IS NULL ORDER BY o.run_after, o.updated_at LIMIT 5", (now(),))
    for job in candidates:
        try:
            contribution = build_contribution(db, job["asset_id"])
            if not contribution:
                # An unfinished or empty analysis must not occupy every bounded batch forever.
                db.x("UPDATE community_outbox SET run_after=? WHERE asset_id=? AND status != 'suppressed'",
                     (now() + 300, job["asset_id"]))
                continue
            body = contribution.model_dump_json()
            digest = hashlib.sha256(body.encode()).hexdigest()
            if job["digest"] == digest and job["destination"] == endpoint:
                db.x("UPDATE community_outbox SET run_after=? WHERE asset_id=?", (now() + 300, job["asset_id"]))
                continue
            from ..ingest.scan import content_hash
            asset = db.q1("SELECT path, local_path FROM assets WHERE id=?", (job["asset_id"],))
            if not asset or content_hash(asset["local_path"] or asset["path"]) != job["imported_hash"]:
                raise Ineligible("The downloaded file was changed locally")
            # Recheck after hashing: a user may have opted out or changed the analysis meanwhile.
            if not settings.community_enabled or settings.community_url.rstrip("/") != endpoint:
                break
            current = build_contribution(db, job["asset_id"])
            if current is None or current.model_dump_json() != body:
                db.x("UPDATE community_outbox SET run_after=? WHERE asset_id=? AND status != 'suppressed'",
                     (now() + 300, job["asset_id"]))
                continue
            if content_hash(asset["local_path"] or asset["path"]) != job["imported_hash"]:
                raise Ineligible("The downloaded file was changed locally")
            if len(body.encode()) > 2 * 1024 * 1024:
                raise Ineligible("Analysis exceeds the community contribution size limit")
            if not settings.community_enabled or settings.community_url.rstrip("/") != endpoint:
                break
            with httpx.Client(timeout=45, follow_redirects=False, transport=transport, trust_env=False) as client:
                response = client.post(endpoint + "/v1/contributions", content=body, headers={"Content-Type": "application/json"})
                if response.status_code in (400, 403, 413, 422):
                    raise Ineligible("The service rejected this contribution")
                response.raise_for_status()
            db.x("UPDATE community_outbox SET digest=?, destination=?, status='shared', attempts=0, run_after=?, message='Shared',"
                 " updated_at=? WHERE asset_id=? AND status != 'suppressed'", (digest, endpoint, now() + 300, now(), job["asset_id"]))
            sent += 1
        except Ineligible:
            db.x("UPDATE community_outbox SET status='suppressed', message='Import is not eligible for sharing', updated_at=?"
                 " WHERE asset_id=?", (now(), job["asset_id"]))
        except Exception:
            attempts = job["attempts"] + 1
            # No response body, URLs or yt-dlp output in logs or status: they can contain credentials/server details.
            db.x("UPDATE community_outbox SET status='pending', attempts=?, run_after=?, message='Community unavailable; will retry',"
                 " updated_at=? WHERE asset_id=? AND status != 'suppressed'", (attempts, now() + min(3600, 30 * 2 ** min(attempts, 7)), now(), job["asset_id"]))
            log.debug("Community contribution deferred for asset %s", job["asset_id"])
    return sent


def status(db: Database, settings: Settings) -> dict:
    counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM community_outbox GROUP BY status")}
    return {"enabled": settings.community_enabled, "configured": bool(settings.community_url), "url": settings.community_url,
            "counts": counts, "state": "off" if not settings.community_enabled else "ready" if settings.community_url else "needs_endpoint"}


def search(settings: Settings, query: str, limit: int = 20, offset: int = 0) -> dict:
    if not settings.community_url:
        raise ValueError("The community service has not been configured")
    with httpx.Client(timeout=45, follow_redirects=False, trust_env=False) as client:
        response = client.get(validate_endpoint(settings.community_url) + "/v1/search",
                              params={"q": query, "limit": limit, "offset": offset})
        response.raise_for_status()
        return response.json()


def start(settings: Settings, stop: threading.Event) -> threading.Thread:
    def loop():
        db = Database(settings.db_path)
        try:
            while not stop.is_set():
                try:
                    sync_once(db, settings)
                except Exception:
                    log.exception("Community sync loop failed")
                stop.wait(30)
        finally:
            db.close()
    thread = threading.Thread(target=loop, name="community-sync", daemon=True)
    thread.start()
    return thread
