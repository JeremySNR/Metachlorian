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


def classify_endpoint(url: str) -> tuple[bool, str]:
    """Is this endpoint on this machine or a private network? Decided from the host, never from a
    user's say-so: loopback, private (RFC 1918 / ULA), link-local and ``.local``/``.lan``/``.internal``
    names are local, as are names that resolve only to such addresses. Anything else is remote."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    host = (urlparse(url if "://" in url else "http://" + url).hostname or "").lower()
    if not host:
        return False, "no host"

    def private(ip: str) -> bool:
        a = ipaddress.ip_address(ip.split("%")[0])
        return a.is_loopback or a.is_private or a.is_link_local

    try:
        return (True, "private address") if private(host) else (False, "public address")
    except ValueError:
        pass
    if host == "localhost" or host.endswith((".localhost", ".local", ".lan", ".internal", ".home.arpa")):
        return True, "local name"
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(host, None)}
    except OSError:
        return False, "name does not resolve"
    if addrs and all(private(a) for a in addrs):
        return True, "resolves to a private address"
    return False, "resolves to a public address"


# Hosted and subscription providers. Models are defaults the admin can change; any OpenAI-compatible
# server (llama.cpp, Ollama, LM Studio, vLLM, Azure, Groq...) is the "custom" provider.
PROVIDERS: dict[str, dict[str, Any]] = {
    "custom": {"label": "Local or custom server (OpenAI-compatible)", "base_url": "", "hosted": False, "key": None,
               "vlm_model": "", "llm_model": "", "concurrency": 1, "batch": 1},
    "openai": {"label": "OpenAI API key", "base_url": "https://api.openai.com/v1", "hosted": True, "key": "openai_api_key",
               "vlm_model": "gpt-5.4-mini", "llm_model": "gpt-5.4-mini", "concurrency": 4, "batch": 1},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "hosted": True, "key": "openrouter_api_key",
                   "vlm_model": "openai/gpt-5.4-mini", "llm_model": "openai/gpt-5.4-mini", "concurrency": 4, "batch": 1},
    "codex": {"label": "ChatGPT subscription via Codex CLI", "base_url": "", "hosted": True, "key": None,
              "vlm_model": "gpt-5.6-luna", "llm_model": "gpt-5.6-luna", "concurrency": 1, "batch": 6, "daily_limit": 200},
}


@dataclass
class ModelEndpoint:
    """An OpenAI-compatible chat endpoint used for VLM captioning or text fusion.

    ``local`` is the admin's declaration; the endpoint only counts as local when
    its host is also local (``classify_endpoint``), so a hosted API can never be
    mislabelled. Remote endpoints are hosted adapters: content leaves the
    machine, so they are refused unless ``allow_remote`` is set.
    """

    provider: str = "custom"  # custom | openai | openrouter | codex (see PROVIDERS)
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""  # name of the env var holding the key, never the key itself
    local: bool = True
    timeout_s: float = 600.0
    max_images: int = 4
    temperature: float = 0.1
    # Extra JSON merged into every request, e.g. {"chat_template_kwargs": {"enable_thinking": false}}
    # for reasoning models served by llama.cpp/vLLM.
    extra_body: dict = field(default_factory=dict)
    concurrency: int = 0      # parallel requests; 0 = the provider's default
    batch: int = 0            # shots per request; 0 = the provider's default
    daily_limit: int = 0      # requests per UTC day (Codex); 0 = the provider's default
    codex_path: str = "codex"

    @property
    def preset(self) -> dict[str, Any]:
        return PROVIDERS.get(self.provider, PROVIDERS["custom"])

    @property
    def url(self) -> str:
        if self.provider in ("openai", "openrouter"):
            return self.preset["base_url"]  # a custom address kept from the Local setting does not apply
        return (self.base_url or self.preset["base_url"]).rstrip("/")

    @property
    def enabled(self) -> bool:
        if self.provider == "codex":
            return bool(self.model)
        return bool(self.url and self.model)

    @property
    def hosted(self) -> bool:
        return bool(self.preset["hosted"])

    @property
    def is_local(self) -> bool:
        if self.hosted:
            return False
        return self.local and classify_endpoint(self.url)[0]

    @property
    def effective_concurrency(self) -> int:
        return max(1, self.concurrency or self.preset.get("concurrency", 1))

    @property
    def effective_batch(self) -> int:
        return max(1, min(8, self.batch or self.preset.get("batch", 1)))

    @property
    def effective_daily_limit(self) -> int:
        return self.daily_limit or self.preset.get("daily_limit", 0)


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
    # ANN index precision: f16 (default) or i8 (half the memory, for very large libraries).
    vector_dtype: str = field(default_factory=lambda: os.environ.get("METACHLORIAN_VECTOR_DTYPE", "f16"))
    # Watch folders (local paths) and object storage sources (s3://bucket/prefix).
    sources: list[str] = field(default_factory=list)
    # VLM for captioning and LLM for fusion / query parsing.
    vlm: ModelEndpoint = field(default_factory=ModelEndpoint)
    llm: ModelEndpoint = field(default_factory=ModelEndpoint)
    allow_remote: bool = False
    # Face identity (recognise and name people). On by default: embeddings stay in this library and are
    # never sent to any provider. Admins can switch it off and forget people individually.
    face_identity: bool = True
    # Imports from web links (YouTube, Vimeo... via yt-dlp). Browser whose login yt-dlp may borrow for private
    # videos (chrome, edge, firefox, brave, opera, vivaldi, safari; only on the machine running the server),
    # the default quality cap, and an optional yt-dlp executable (else PATH, else downloaded on first use).
    # Camera raw that FFmpeg cannot read: a command per file extension that converts it to a working master
    # the rest of the pipeline reads, e.g. {"r3d": "REDline --i {input} --o {output_stem} ..."}. Placeholders:
    # {input} (the raw file), {output} (the .mov to write), {output_stem} (it without the extension), {output_dir}.
    raw_decoders: dict = field(default_factory=dict)
    import_cookies_browser: str = ""
    import_max_height: int = 1080
    ytdlp_path: str = ""
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
        return ep.enabled and (ep.is_local or self.allow_remote)

    def egress_summary(self) -> dict[str, Any]:
        """What, if anything, can leave this machine. Shown in the UI."""
        items = []
        for name, ep in (("vlm", self.vlm), ("llm", self.llm)):
            if ep.enabled and not ep.is_local:
                items.append({
                    "adapter": name,
                    "provider": ep.provider,
                    "base_url": ep.url if ep.provider != "codex" else "codex exec (ChatGPT)",
                    "model": ep.model,
                    "active": self.allow_remote,
                    "sends": ("sampled keyframes as contact sheets, transcript and on-screen text snippets, measured facts" if name == "vlm"
                              else "shot captions, transcript snippets and measured facts, for summaries and roles"),
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
        for f in ("PROVIDER", "BASE_URL", "MODEL", "API_KEY_ENV"):
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
