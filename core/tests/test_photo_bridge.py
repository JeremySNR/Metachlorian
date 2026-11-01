"""Exercise the real localhost transport including framing and lost responses."""
import json
import socket
import threading

import pytest

from metachlorian.photos.bridge import LightroomBridge
from metachlorian.photos.errors import LightroomUnavailable, PhotoConflict, PhotoError


@pytest.fixture
def connector(tmp_path):
    request, response = socket.socket(), socket.socket()
    request.bind(('127.0.0.1', 0)); response.bind(('127.0.0.1', 0))
    request.listen(); response.listen()
    token = tmp_path/'token'; token.write_text('a'*64)
    bridge = LightroomBridge(request.getsockname()[1], response.getsockname()[1], token)
    handlers, errors = [], []
    def serve():
        try:
            with response.accept()[0] as outbound, request.accept()[0] as inbound:
                inbound.settimeout(3)
                with inbound.makefile('rb') as reader:
                    for line in reader:
                        payload = json.loads(line)
                        assert payload['hello'] == 'a'*64
                        handler = handlers.pop(0)
                        result = handler(payload)
                        if result is None:
                            break
                        data = (json.dumps({'id': payload['id'], **result})+'\n').encode()
                        # Intentionally split a JSON response across TCP reads.
                        outbound.sendall(data[:7]); outbound.sendall(data[7:])
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield bridge, handlers
    bridge.close(); request.close(); response.close(); thread.join(4)
    assert not errors


def test_transport_authentication_framing_conflict_and_readback(connector):
    bridge, handlers = connector
    handlers.extend([lambda p: {'result': {'catalog': {'uid': 'family'}}}, lambda p: {'error': 'CONFLICT: changed'}, lambda p: {'error': 'Unsupported Lightroom setting'}])
    assert bridge.call('mc_status')['catalog']['uid'] == 'family'
    with pytest.raises(PhotoConflict, match='changed'):
        bridge.call('mc_apply', {'operation_id': 'one'})
    with pytest.raises(PhotoError, match='Unsupported'):
        bridge.call('mc_context')
    with pytest.raises(PhotoError, match='Unsupported connector action'):
        bridge.call('execute_lua')


def test_transport_does_not_replay_a_lost_write(connector):
    bridge, handlers = connector
    requests = []
    handlers.append(lambda payload: requests.append(payload) or None)
    with pytest.raises(LightroomUnavailable):
        bridge.call('mc_apply', {'operation_id': 'write-once'}, timeout=2)
    assert len(requests) == 1


def test_missing_token_and_bad_token_are_offline(tmp_path):
    bridge = LightroomBridge(token_path=tmp_path/'token')
    assert bridge.status()['code'] == 'connector_not_started'
    bridge.token_path.write_text('short')
    assert bridge.status(force=True)['code'] == 'invalid_token'


@pytest.mark.parametrize('invalid', [{'protocol': 99, 'catalog': {'uid': 'family'}}, {'protocol': 1, 'catalog': None}, {'protocol': 1, 'catalog': {'uid': 'family'}, 'capabilities': []}])
def test_status_verifies_protocol_and_caches_success(connector, invalid):
    bridge, handlers = connector
    handlers.extend([lambda p: {'result': {'protocol': 1, 'catalog': {'uid': 'family'}, 'connector_version': '0.2.0'}},
                     lambda p: {'result': invalid}])
    first = bridge.status()
    assert first['connected'] and first['checked_at'] == first['last_connected_at']
    assert bridge.status() == first and len(handlers) == 1
    assert bridge.status(force=True)['code'] == 'protocol_mismatch'


def test_status_does_not_block_on_inflight_render(tmp_path):
    bridge = LightroomBridge(token_path=tmp_path/'token')
    entered, release = threading.Event(), threading.Event()
    def render():
        with bridge._lock:
            entered.set(); release.wait(3)
    thread = threading.Thread(target=render); thread.start(); entered.wait(1)
    try:
        assert bridge.status(force=True)['busy']
    finally:
        release.set(); thread.join()
