"""Hosted model providers: key storage, request shape, fallbacks, the Codex CLI adapter and its daily cap."""
import json
import os
import stat
import sys
import textwrap

import httpx
import pytest

from metachlorian import apikeys, llm
from metachlorian.config import ModelEndpoint, Settings

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["caption", "tags"],
          "properties": {"caption": {"type": "string", "minLength": 5, "maxLength": 40},
                         "tags": {"type": "array", "items": {"enum": ["a", "b"]}, "maxItems": 1}}}


def _settings(tmp_path, **kw) -> Settings:
    s = Settings()
    s.data_dir = tmp_path
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_api_keys_are_private_masked_and_fall_back_to_env(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert apikeys.get(s, "openai_api_key") == ""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-0000000000000000")
    assert apikeys.status(s)["openai_api_key"]["from"] == "environment"
    apikeys.put(s, "openai_api_key", "sk-proj-abcdefghijklmnop1234")
    assert apikeys.get(s, "openai_api_key") == "sk-proj-abcdefghijklmnop1234"
    st = apikeys.status(s)["openai_api_key"]
    assert st["from"] == "stored" and st["masked"] == "sk-pr…1234" and "abcdefgh" not in st["masked"]
    assert stat.S_IMODE(os.stat(tmp_path / "secrets.json").st_mode) == 0o600
    with pytest.raises(ValueError):
        apikeys.put(s, "openai_api_key", "has space")
    apikeys.put(s, "openai_api_key", "")
    assert apikeys.status(s)["openai_api_key"]["from"] == "environment"


def test_strict_schema_and_coerce():
    st = llm.strict_schema(SCHEMA)
    assert "minLength" not in json.dumps(st) and "maxItems" not in json.dumps(st) and "minLength" in json.dumps(SCHEMA)
    assert llm.coerce({"caption": "x" * 60, "tags": ["a", "b"]}, SCHEMA) == {"caption": "x" * 40, "tags": ["a"]}


def _mock_client(monkeypatch, handler):
    real = httpx.Client

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(llm.httpx, "Client", factory)


def test_hosted_providers_need_consent_and_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    ep = ModelEndpoint(provider="openrouter", model="openai/gpt-5.4-mini")
    assert ep.enabled and ep.hosted and not ep.is_local and ep.url == "https://openrouter.ai/api/v1"
    with pytest.raises(llm.LLMError, match="allow_remote"):
        llm.make_client(ep, _settings(tmp_path))
    with pytest.raises(llm.LLMError, match="no API key"):
        llm.make_client(ep, _settings(tmp_path, allow_remote=True))


def test_openrouter_request_shape_and_structured_output_fallback(tmp_path, monkeypatch):
    s = _settings(tmp_path, allow_remote=True)
    apikeys.put(s, "openrouter_api_key", "sk-or-v1-0123456789abcdef")
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append((dict(req.headers), body))
        if body.get("response_format", {}).get("type") == "json_schema":
            return httpx.Response(400, json={"error": {"message": "json_schema is not supported for this model"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"caption": "A pier at dusk", "tags": ["a", "b"]}\n```'}}],
                                         "usage": {"total_tokens": 42}})

    _mock_client(monkeypatch, handler)
    client = llm.make_client(ModelEndpoint(provider="openrouter", model="openai/gpt-5.4-mini"), s)
    obj, usage = client.structured([{"role": "user", "content": "log it"}], SCHEMA)
    assert obj == {"caption": "A pier at dusk", "tags": ["a"]} and usage["total_tokens"] == 42
    h0, b0 = seen[0]
    assert h0["authorization"] == "Bearer sk-or-v1-0123456789abcdef" and h0["x-title"] == "Metachlorian"
    assert "minLength" not in json.dumps(b0["response_format"]) and "temperature" not in b0
    assert seen[1][1]["response_format"] == {"type": "json_object"}


def test_openai_uses_max_completion_tokens_and_reports_bad_keys(tmp_path, monkeypatch):
    s = _settings(tmp_path, allow_remote=True)
    apikeys.put(s, "openai_api_key", "sk-proj-0123456789abcdef")
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(401, json={"error": "bad key"})

    _mock_client(monkeypatch, handler)
    client = llm.make_client(ModelEndpoint(provider="openai", model="gpt-5.4-mini"), s)
    with pytest.raises(llm.LLMError, match="rejected the API key"):
        client.chat([{"role": "user", "content": "hi"}], SCHEMA)
    assert "max_completion_tokens" in bodies[0] and "max_tokens" not in bodies[0]


FAKE_CODEX = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    args = sys.argv[1:]
    if args[:2] == ["login", "status"]:
        print("Logged in using ChatGPT"); sys.exit(0)
    assert args[0] == "exec" and "--sandbox" in args and args[args.index("--sandbox") + 1] == "read-only"
    assert "OPENAI_API_KEY" not in os.environ, "an API key leaked into codex"
    prompt = sys.stdin.read()
    out = args[args.index("--output-last-message") + 1]
    images = [a for i, a in enumerate(args) if i and args[i - 1] == "--image"]
    assert all(os.path.exists(p) for p in images)
    with open(os.environ["FAKE_CODEX_LOG"], "a") as f:
        f.write(json.dumps({{"images": len(images), "prompt_has_untrusted_note": "untrusted" in prompt}}) + "\\n")
    with open(out, "w") as f:
        f.write(json.dumps({{"caption": "A wide shot of a harbour", "tags": ["b"]}}))
''')


def test_codex_adapter_uses_the_subscription_caches_and_caps(tmp_path, monkeypatch):
    exe = tmp_path / "codex"
    exe.write_text(FAKE_CODEX.format(python=sys.executable))
    exe.chmod(0o755)
    log = tmp_path / "codex.log"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-be-used-000000")
    ep = ModelEndpoint(provider="codex", model="gpt-5.6-luna", codex_path=str(exe), daily_limit=2)
    s = _settings(tmp_path, allow_remote=True)
    assert llm.codex_status(ep)["ok"]
    client = llm.make_client(ep, s)
    img = tmp_path / "f.jpg"
    import cv2
    import numpy as np

    cv2.imwrite(str(img), np.zeros((16, 16, 3), np.uint8))
    msgs = [{"role": "user", "content": [llm.image_part(img), {"type": "text", "text": "log it"}]}]
    obj, _ = client.structured(msgs, SCHEMA)
    assert obj == {"caption": "A wide shot of a harbour", "tags": ["b"]}
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    assert calls == [{"images": 1, "prompt_has_untrusted_note": True}]
    client.structured(msgs, SCHEMA)  # identical request: served from the cache, no new request
    assert len(log.read_text().splitlines()) == 1 and llm.codex_remaining(s, ep) == 1
    other = [{"role": "user", "content": "another shot"}]
    client.structured(other, SCHEMA)
    assert llm.codex_remaining(s, ep) == 0
    with pytest.raises(llm.LimitReached):
        client.structured([{"role": "user", "content": "a third"}], SCHEMA)
