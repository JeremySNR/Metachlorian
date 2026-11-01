"""Authenticated, serial, localhost-only client for the bundled Lua connector."""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from pathlib import Path

from .errors import LightroomUnavailable, PhotoConflict, PhotoError

MAX_RESPONSE = 24 * 1024 * 1024


class LightroomBridge:
    def __init__(self, request_port: int = 58773, response_port: int = 58774, token_path: Path | None = None):
        self.request_port, self.response_port = request_port, response_port
        self.token_path = token_path or Path.home() / '.config' / 'metachlorian-lightroom' / 'token'
        self._lock = threading.RLock()
        self._request = self._response = None
        self._buffer = b''
        self._last_used = 0.0

    def close(self):
        with self._lock:
            for conn in (self._request, self._response):
                if conn:
                    conn.close()
            self._request = self._response = None
            self._buffer = b''

    def _connect(self):
        self.close()
        try:
            # Attach the response channel first: Lightroom can then answer the
            # first request without racing the send-side connection callback.
            self._response = socket.create_connection(('127.0.0.1', self.response_port), timeout=3)
            self._request = socket.create_connection(('127.0.0.1', self.request_port), timeout=3)
        except OSError:
            self.close()
            raise

    def call(self, action: str, params: dict | None = None, *, timeout: float = 120) -> dict:
        if action not in {'mc_status', 'mc_catalog_page', 'mc_context', 'mc_preview', 'mc_render', 'mc_begin', 'mc_apply', 'mc_finish', 'mc_restore', 'mc_import', 'ping'}:
            raise PhotoError('Unsupported connector action')
        with self._lock:
            try:
                token = self.token_path.read_text().strip()
                if not 32 <= len(token) <= 256:
                    raise OSError('invalid connector token')
                if self._request is None or time.monotonic() - self._last_used > 60:
                    self._connect()
                request_id = uuid.uuid4().hex
                payload = json.dumps({'id': request_id, 'hello': token, 'action': action, 'params': params or {}}, allow_nan=False)
                self._request.sendall(payload.encode() + b'\n')
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if b'\n' not in self._buffer:
                        self._response.settimeout(max(.1, deadline - time.monotonic()))
                        chunk = self._response.recv(65536)
                        if not chunk:
                            raise OSError('connector disconnected')
                        self._buffer += chunk
                        if len(self._buffer) > MAX_RESPONSE:
                            self.close()
                            raise PhotoError('Lightroom response exceeded the size limit')
                        continue
                    line, self._buffer = self._buffer.split(b'\n', 1)
                    if not line:
                        continue
                    response = json.loads(line)
                    if response.get('id') != request_id:
                        continue
                    self._last_used = time.monotonic()
                    if response.get('error'):
                        message = str(response['error'])
                        if 'CONFLICT:' in message:
                            raise PhotoConflict(message)
                        raise PhotoError(message)
                    return response.get('result') or {}
                raise TimeoutError('Lightroom operation timed out')
            except (OSError, TimeoutError, json.JSONDecodeError) as exc:
                self.close()
                # Never replay a mutation here: the durable job and connector
                # receipt determine whether a lost response can be recovered.
                raise LightroomUnavailable('Open Lightroom Classic and enable the Metachlorian Photos connector. '
                                           'If a write was interrupted, resume its job to reconcile the result.') from exc

    def status(self) -> dict:
        try:
            return {'connected': True, **self.call('mc_status', timeout=5)}
        except (LightroomUnavailable, PhotoError) as exc:
            return {'connected': False, 'message': str(exc)}
