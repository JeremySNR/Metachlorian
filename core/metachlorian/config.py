"""Runtime configuration.

Configuration comes from (lowest to highest precedence): built-in defaults,
``<data_dir>/config.toml``, then ``METACHLORIAN_*`` environment variables.
Everything that can send content off the machine is off by default and is
reported by :func:`Settings.egress_summary` so the UI can show it.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _default_data_dir() -> Path:
    env = os.environ.get("METACHLORIAN_DATA")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "metachlorian"


@dataclass
class ModelEndpoint:
    """An OpenAI-compatible chat endpoint used for VLM captioning or text fusion.

    ``local`` must be true only for endpoints on this machine or LAN that the
    admin controls. Remote endpoints are hosted adapters: content leaves the
    machine, so they are refused unless ``allow_remote`` is set.
    """

    base_url: str = ""
    model: str = ""
    api_key_env: str = ""  # name of the env var holding the key, never the key itself
    local: bool = True
    timeout_s: float = 600.0
    max_images: int = 4
    temperature: float = 0.1

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    models_dir: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    # Worker processes for analysis. 0 = run in-process threads only (tests).
    workers: int = 2
    # Proxy rendition used for analysis and playback.
    proxy_height: int = 540
    proxy_crf: int = 26
    # Seconds between sprite frames for hover scrubbing.
    sprite_interval: float = 1.0
    # Segment long single takes into parts no longer than this (seconds).
    max_segment_s: float = 20.0
    # Watch folders (local paths) and object storage sources (s3://bucket/prefix).
    sources: list[str] = field(default_factory=list)
    # VLM for captioning and LLM for fusion / query parsing.
    vlm: ModelEndpoint = field(default_factory=ModelEndpoint)
    llm: ModelEndpoint = field(default_factory=ModelEndpoint)
    allow_remote: bool = False
    # Opt-in features.
    face_identity: bool = False
    # Auth: when false (solo mode on loopback) requests from 127.0.0.1 act as
    # the local admin. Team mode must set this to true.
    require_auth: bool = False
    secret_key: str = ""
    cors_origins: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.data_dir / "library.sqlite"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def resolved_models_dir(self) -> Path:
        if self.models_dir:
            return Path(self.models_dir)
        env = os.environ.get("METACHLORIAN_MODELS")
        return Path(env) if env else self.data_dir / "models"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.media_dir, self.index_dir, self.export_dir, self.resolved_models_dir):
            p.mkdir(parents=True, exist_ok=True)

    def endpoint_allowed(self, ep: ModelEndpoint) -> bool:
        return ep.enabled and (ep.local or self.allow_remote)

    def egress_summary(self) -> dict[str, Any]:
        """What, if anything, can leave this machine. Shown in the UI."""
        items = []
        for name, ep in (("vlm", self.vlm), ("llm", self.llm)):
            if ep.enabled and not ep.local:
                items.append({
                    "adapter": name,
                    "base_url": ep.base_url,
                    "model": ep.model,
                    "active": self.allow_remote,
                    "sends": "sampled keyframes and analyser text" if name == "vlm" else "analyser text and queries",
                })
        return {"content_leaves_machine": any(i["active"] for i in items), "adapters": items}

    def public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["data_dir"] = str(self.data_dir)
        d["models_dir"] = str(self.resolved_models_dir)
        d.pop("secret_key", None)
        return d


def _apply(obj: Any, data: dict[str, Any]) -> None:
    for k, v in data.items():
        if not hasattr(obj, k):
            continue
        cur = getattr(obj, k)
        if isinstance(cur, ModelEndpoint) and isinstance(v, dict):
            _apply(cur, v)
        elif isinstance(cur, Path) or k in ("data_dir", "models_dir"):
            setattr(obj, k, Path(v).expanduser() if v else None)
        else:
            setattr(obj, k, v)


def _env_overrides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    p = "METACHLORIAN_"
    simple = {"HOST": "host", "PORT": "port", "WORKERS": "workers", "REQUIRE_AUTH": "require_auth",
              "ALLOW_REMOTE": "allow_remote", "SECRET_KEY": "secret_key", "MODELS": "models_dir"}
    for env, key in simple.items():
        if (v := os.environ.get(p + env)) is not None:
            if key in ("port", "workers"):
                out[key] = int(v)
            elif key in ("require_auth", "allow_remote"):
                out[key] = v.lower() in ("1", "true", "yes", "on")
            else:
                out[key] = v
    for ep in ("VLM", "LLM"):
        d = {}
        for f in ("BASE_URL", "MODEL", "API_KEY_ENV"):
            if (v := os.environ.get(f"{p}{ep}_{f}")) is not None:
                d[f.lower()] = v
        if (v := os.environ.get(f"{p}{ep}_LOCAL")) is not None:
            d["local"] = v.lower() in ("1", "true", "yes")
        if d:
            out[ep.lower()] = d
    if (v := os.environ.get(p + "SOURCES")):
        out["sources"] = [s for s in v.split(os.pathsep) if s]
    return out


def load_settings(data_dir: str | Path | None = None, **overrides: Any) -> Settings:
    s = Settings()
    if data_dir:
        s.data_dir = Path(data_dir).expanduser()
    cfg = s.data_dir / "config.toml"
    if cfg.exists():
        _apply(s, tomllib.loads(cfg.read_text()))
    _apply(s, _env_overrides())
    _apply(s, overrides)
    if data_dir:
        s.data_dir = Path(data_dir).expanduser()
    return s
