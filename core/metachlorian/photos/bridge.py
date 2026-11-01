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
        self._status = None
        self._status_at = 0.0
        self._last_success = None

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
        if action not in {'mc_status', 'mc_find_photo', 'mc_catalog_page', 'mc_context', 'mc_preview', 'mc_render', 'mc_begin', 'mc_apply', 'mc_finish', 'mc_restore', 'mc_import', 'ping'}:
            raise PhotoError('Unsupported connector action')
        with self._lock:
            try:
                token = self.token_path.read_text().strip()
                if not 32 <= len(token) <= 256:
                    raise LightroomUnavailable('The Lightroom connector token is incomplete. Restart the Metachlorian Photos plug-in in Lightroom, then check the connection again.', 'invalid_token')
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
                    if not isinstance(response, dict):
                        raise LightroomUnavailable('The service on the Lightroom ports returned an invalid response. Check that the Metachlorian Photos connector uses the same ports.', 'invalid_response')
                    if response.get('id') != request_id:
                        continue
                    self._last_used = time.monotonic()
                    if response.get('error'):
                        message = str(response['error'])
                        if 'CONFLICT:' in message:
                            raise PhotoConflict(message)
                        raise PhotoError(message)
                    result = response.get('result') or {}
                    if not isinstance(result, dict):
                        raise LightroomUnavailable('The Lightroom connector returned an invalid result. Update the connector files and reload the plug-in.', 'invalid_response')
                    return result
                raise TimeoutError('Lightroom operation timed out')
            except LightroomUnavailable:
                self.close()
                self._status = None
                raise
            except (OSError, TimeoutError, json.JSONDecodeError) as exc:
                self.close()
                self._status = None
                # Never replay a mutation here: the durable job and connector
                # receipt determine whether a lost response can be recovered.
                if isinstance(exc, FileNotFoundError):
                    code, message = 'connector_not_started', 'Lightroom has not started the Metachlorian Photos connector for this OS account. Add it in File → Plug-in Manager, enable it, then use Start connection or restart Lightroom.'
                elif isinstance(exc, PermissionError):
                    code, message = 'token_unreadable', 'Metachlorian cannot read the Lightroom connector token. Run both applications under the same OS account and check the token file permissions.'
                elif isinstance(exc, (TimeoutError, socket.timeout)):
                    code, message = 'response_timeout', 'Lightroom did not answer. It may be busy, the plug-in may need restarting, or the connection ports may differ. Check Metachlorian Photos in Lightroom’s Plug-in Manager.'
                elif isinstance(exc, json.JSONDecodeError):
                    code, message = 'invalid_response', 'The connection returned invalid data. Update and reload the Metachlorian Photos connector; confirm its ports match this library.'
                else:
                    code, message = 'connection_refused', f'No Lightroom connector is answering on ports {self.request_port}/{self.response_port}. Open Lightroom Classic, start the Metachlorian Photos connector and check its port settings.'
                if action in {'mc_begin', 'mc_apply', 'mc_finish', 'mc_restore', 'mc_import'}:
                    message += ' Resume the interrupted job in Activity after reconnecting.'
                raise LightroomUnavailable(message, code) from exc

    def status(self, *, force: bool = False) -> dict:
        # Status polling must never wait behind a multi-minute Lightroom render.
        if not self._lock.acquire(blocking=False):
            return {**(self._status or {'connected': False}), 'busy': True,
                    'message': 'Lightroom is processing a request. Connection details will refresh when it finishes.'}
        try:
            if not force and self._status is not None and time.monotonic() - self._status_at < 5:
                return self._status.copy()
            checked = time.time()
            try:
                result = self.call('mc_status', timeout=5)
                if (result.get('protocol') != 1 or not isinstance(result.get('catalog'), dict)
                        or not result['catalog'].get('uid') or not isinstance(result.get('capabilities', {}), dict)):
                    raise LightroomUnavailable('The connected service is not a compatible Metachlorian Photos connector. Copy the current connector files and reload them in Lightroom.', 'protocol_mismatch')
                self._last_success = checked
                state = {**result, 'connected': True, 'code': 'connected', 'checked_at': checked}
            except (LightroomUnavailable, PhotoError) as exc:
                state = {'connected': False, 'code': getattr(exc, 'code', 'connector_error'), 'message': str(exc), 'checked_at': checked}
            state['last_connected_at'] = self._last_success
            self._status, self._status_at = state, time.monotonic()
            return state.copy()
        finally:
            self._lock.release()
