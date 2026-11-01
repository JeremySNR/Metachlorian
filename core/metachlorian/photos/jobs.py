"""Durable photo jobs with one local runner and explicit interrupted-write recovery."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

from ..db import dumps, loads, now
from ..auth import audit
from ..ingest.scan import new_uid
from .errors import LightroomUnavailable, PhotoConflict, PhotoError


class Cancelled(Exception):
    pass


class YieldToEdits(Exception):
    """Keep the analysis checkpoint and give interactive work the next turn."""
    pass


def job_scope(kind: str) -> str:
    return 'admin' if kind == 'models' else 'photos:edit' if kind in {'begin', 'apply', 'finish', 'restore'} else 'ingest:write'


class PhotoJobs:
    def __init__(self, service):
        self.service, self.db = service, service.db
        self._thread = None
        self._guard = threading.Lock()
        self._stop = threading.Event()
        self.autostart = True

    def enqueue(self, principal, kind: str, request: dict, key: str) -> dict:
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise PhotoError('An idempotency_key of 1 to 200 characters is required')
        payload = json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.db.tx() as c:
            existing = c.execute('SELECT * FROM photo_jobs WHERE owner=? AND kind=? AND idempotency_key=?', (principal.username, kind, key)).fetchone()
            if existing:
                if existing['request_hash'] != digest:
                    raise PhotoConflict('This idempotency key already belongs to a different request')
                uid = existing['uid']
            else:
                uid = new_uid('pj')
                actor = {**principal.as_dict(), 'token_id': principal.token_id}
                c.execute('INSERT INTO photo_jobs(uid,owner,kind,idempotency_key,request_hash,request,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                          (uid, principal.username, kind, key, digest, dumps({'arguments': request, 'actor': actor}), now(), now()))
                audit(self.db, principal, 'queue_photo_'+kind, uid)
        if self.autostart:
            self.start()
        return self.get(uid)

    def get(self, uid: str) -> dict:
        row = self.db.q1('SELECT uid,owner,kind,status,result,error,cancel_requested,created_at,updated_at FROM photo_jobs WHERE uid=?', (uid,))
        if not row:
            raise PhotoError('Photo job not found')
        result = dict(row)
        result['result'] = loads(result['result'], {})
        return result

    def checkpoint(self, uid: str, result: dict | None = None):
        row = self.db.q1('SELECT cancel_requested FROM photo_jobs WHERE uid=?', (uid,))
        if self._stop.is_set() or row['cancel_requested']:
            raise Cancelled()
        if result is not None:
            self.db.x('UPDATE photo_jobs SET result=?,updated_at=? WHERE uid=?', (dumps(result), now(), uid))

    def run_once(self) -> bool:
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM photo_jobs WHERE status='queued' ORDER BY CASE WHEN kind IN ('begin','apply','finish','restore') THEN 0 WHEN kind='analyse' THEN 2 ELSE 1 END,created_at LIMIT 1").fetchone()
            if not row:
                return False
            c.execute("UPDATE photo_jobs SET status='running',updated_at=? WHERE uid=?", (now(), row['uid']))
        job = dict(row)
        try:
            self.checkpoint(job['uid'])
            result = self.service.execute(job)
            self.db.x("UPDATE photo_jobs SET status='done',result=?,error=NULL,updated_at=? WHERE uid=?", (dumps(result), now(), job['uid']))
        except YieldToEdits:
            self.db.x("UPDATE photo_jobs SET status='queued',updated_at=? WHERE uid=?", (now(), job['uid']))
        except Cancelled:
            self.db.x("UPDATE photo_jobs SET status='cancelled',updated_at=? WHERE uid=?", (now(), job['uid']))
        except LightroomUnavailable as exc:
            self.db.x("UPDATE photo_jobs SET status='waiting',error=?,updated_at=? WHERE uid=?", (str(exc), now(), job['uid']))
        except PhotoConflict as exc:
            self.db.x("UPDATE photo_jobs SET status='conflict',error=?,updated_at=? WHERE uid=?", (str(exc), now(), job['uid']))
        except Exception as exc:
            self.db.x("UPDATE photo_jobs SET status='failed',error=?,updated_at=? WHERE uid=?", (str(exc)[:2000], now(), job['uid']))
        return True

    def start(self):
        with self._guard:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='metachlorian-photos', daemon=True)
            self._thread.start()

    def _run(self):
        root = Path(self.service.settings.data_dir)
        with (root / 'photo-runner.lock').open('a+b') as lock:
            try:
                if os.name == 'nt':
                    import msvcrt
                    if lock.tell() == 0:
                        lock.write(b'0')
                        lock.flush()
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return  # The existing core owns the shared queue.
            try:
                # A runner held this lock for its entire lifetime. Only now is
                # it safe to classify another runner's in-flight jobs as lost.
                self.db.x("UPDATE photo_jobs SET status='waiting',error='Runner interrupted. Resume to reconcile with Lightroom.' WHERE status='running'")
                while not self._stop.is_set():
                    if not self.service.settings.photos_enabled or not self.run_once():
                        self._stop.wait(.5)
            finally:
                self.db.close()
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
