"""Install a local HTTP MCP connection without changing unrelated client settings.

Invoked by the desktop shell with JSON on stdin; credentials never enter argv.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import tomlkit
from filelock import FileLock


def install(client: str, url: str, token: str, *, home: Path | None = None) -> Path:
    if client not in ('codex', 'claude-code'):
        raise ValueError('Unsupported client')
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != 8765 or parsed.path != '/mcp/' or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Installation requires the local Metachlorian server on port 8765')
    if not isinstance(token, str) or not token.startswith('mc_') or any(c.isspace() for c in token):
        raise ValueError('Create a valid agent token first')
    home = home or Path.home()
    target = (Path(os.environ.get('CODEX_HOME', str(home / '.codex'))) / 'config.toml'
              if client == 'codex' else home / '.claude.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(target) + '.metachlorian.lock', timeout=10):
        original = target.read_text(encoding='utf-8') if target.exists() else ''
        if client == 'codex':
            config = tomlkit.parse(original)
            config.setdefault('mcp_servers', {})['metachlorian'] = {
                'url': url, 'http_headers': {'Authorization': f'Bearer {token}'}}
            output = tomlkit.dumps(config)
            tomlkit.parse(output)
        else:
            config = json.loads(original) if original.strip() else {}
            config.setdefault('mcpServers', {})['metachlorian'] = {
                'type': 'http', 'url': url, 'headers': {'Authorization': f'Bearer {token}'}}
            output = json.dumps(config, indent=2) + '\n'
        if output == original:
            return target
        # Unique backups preserve the user's previous configuration on every replacement.
        if target.exists():
            fd, backup = tempfile.mkstemp(prefix=target.name + '.backup-', dir=target.parent)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
                f.write(original)
        fd, temporary = tempfile.mkstemp(prefix=target.name + '.', dir=target.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
                f.write(output)
                f.flush()
                os.fsync(f.fileno())
            current = target.read_text(encoding='utf-8') if target.exists() else ''
            if current != original:
                raise RuntimeError('Configuration changed during installation; retry')
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return target


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        target = install(request['client'], request['url'], request['token'])
        print(json.dumps({'ok': True, 'path': str(target)}))
    except Exception:
        # Parser errors can contain configuration secrets. Do not echo them to the renderer/logs.
        print(json.dumps({'ok': False, 'error': 'Could not update the client configuration. Check that it is valid and writable; existing settings were preserved.'}))
        sys.exit(1)
