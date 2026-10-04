"""API keys for hosted model providers.

Stored in ``<data_dir>/secrets.json`` readable only by the server's user (0600),
never written to config.toml, never returned by the API (only a masked form),
and never logged. Environment variables are a fallback, so container and
systemd installs can keep keys in their own secret stores instead.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Settings

KNOWN = {"openai_api_key": "OPENAI_API_KEY", "openrouter_api_key": "OPENROUTER_API_KEY"}


def _path(settings: Settings) -> Path:
    return settings.data_dir / "secrets.json"


def _read(settings: Settings) -> dict[str, str]:
    p = _path(settings)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get(settings: Settings, name: str) -> str:
    """Stored key first, then the conventional environment variable."""
    if name not in KNOWN:
        raise KeyError(name)
    return _read(settings).get(name) or os.environ.get(KNOWN[name], "")


def put(settings: Settings, name: str, value: str) -> None:
    if name not in KNOWN:
        raise ValueError(f"unknown secret '{name}'; expected one of {sorted(KNOWN)}")
    value = (value or "").strip()
    if any(c.isspace() for c in value):
        raise ValueError("an API key cannot contain spaces or line breaks")
    data = _read(settings)
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    p = _path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def mask(value: str) -> str:
    return f"{value[:5]}…{value[-4:]}" if len(value) > 12 else ("set" if value else "")


def status(settings: Settings) -> dict[str, dict[str, str | bool]]:
    stored = _read(settings)
    out = {}
    for name, env in KNOWN.items():
        v = stored.get(name) or os.environ.get(env, "")
        out[name] = {"present": bool(v), "masked": mask(v), "from": "stored" if stored.get(name) else ("environment" if v else "")}
    return out
