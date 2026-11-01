"""A process-safe, byte-bounded cache. No permanent thumbnails or face crops."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import CacheBudgetExceeded


class PreviewCache:
    def __init__(self, root: Path, budget: int):
        self.root = Path(root)
        self.budget = int(budget)
        self.root.mkdir(parents=True, exist_ok=True)
        self._mutex = threading.RLock()

    @contextmanager
    def _locked(self):
        with self._mutex, (self.root / '.lock').open('a+b') as lock:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0)
                if not lock.read(1):
                    lock.write(b'0')
                    lock.flush()
                lock.seek(0)
                while True:
                    try:
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(.05)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                # Only the holder can own staging directories. Leftovers mean
                # a prior process died; recovering must not accumulate exports.
                for p in self.root.glob('scratch-*'):
                    shutil.rmtree(p, ignore_errors=True)
                yield
            finally:
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _path(self, key: str) -> Path:
        return self.root / (hashlib.sha256(key.encode()).hexdigest() + '.jpg')

    def _reserve(self, size: int):
        if size < 0 or size > self.budget:
            raise CacheBudgetExceeded('This rendition exceeds the photo cache budget; request a smaller preview or increase the budget.')
        files = sorted(self.root.glob('*.jpg'), key=lambda p: p.stat().st_mtime_ns)
        total = sum(p.stat().st_size for p in files)
        for p in files:
            if total + size <= self.budget:
                break
            total -= p.stat().st_size
            p.unlink()

    def get(self, key: str) -> bytes | None:
        with self._locked():
            self._reserve(0)
            p = self._path(key)
            if not p.exists():
                return None
            data = p.read_bytes()
            os.utime(p, None)
            return data

    def put(self, key: str, data: bytes) -> None:
        with self._locked():
            p = self._path(key)
            p.unlink(missing_ok=True)
            self._reserve(len(data))
            # A write interrupted by a crash is harmless: readers verify JPEGs.
            p.write_bytes(data)

    @contextmanager
    def scratch(self, reserve: int):
        """Reserve worst-case bytes before asking Lightroom to export.

        Keep the cross-process lock for the complete rendition lifetime. Only
        one full-size temporary render can exist, even with multiple MCP clients.
        """
        with self._locked():
            self._reserve(reserve)
            path = Path(tempfile.mkdtemp(prefix='scratch-', dir=self.root))
            try:
                yield path
                if sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) > reserve:
                    raise CacheBudgetExceeded('Renderer exceeded its reserved byte budget')
            finally:
                shutil.rmtree(path, ignore_errors=True)

    def stats(self) -> dict:
        with self._locked():
            self._reserve(0)
            files = list(self.root.glob('*.jpg'))
            return {'bytes': sum(p.stat().st_size for p in files), 'budget_bytes': self.budget, 'files': len(files)}

    def clear(self):
        with self._locked():
            for p in self.root.glob('*.jpg'):
                p.unlink()
