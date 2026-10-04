"""Minimal client for OpenAI-compatible chat endpoints (llama.cpp server,
Ollama, LM Studio, vLLM, or an opt-in hosted API) with JSON-schema output,
validation and one corrective retry."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
import jsonschema

from .config import ModelEndpoint, Settings


class LLMError(Exception):
    pass


class ValidationFailed(LLMError):
    def __init__(self, msg: str, raw: str):
        super().__init__(msg)
        self.raw = raw


def image_part(path: str | Path, max_side: int = 768) -> dict[str, Any]:
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        raise LLMError(f"cannot read {path}")
    h, w = img.shape[:2]
    s = max_side / max(h, w)
    if s < 1:
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()}}


def _extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


class ChatClient:
    def __init__(self, ep: ModelEndpoint, settings: Settings):
        if not ep.enabled:
            raise LLMError("endpoint not configured")
        if not ep.local and not settings.allow_remote:
            raise LLMError("remote model endpoints are disabled (allow_remote=false): content would leave this machine")
        self.ep = ep
        key = os.environ.get(ep.api_key_env, "") if ep.api_key_env else ""
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.base = ep.base_url.rstrip("/")
        self.supports_schema = True

    def chat(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None, max_tokens: int = 900) -> tuple[str, dict[str, Any]]:
        body: dict[str, Any] = {"model": self.ep.model, "messages": messages, "temperature": self.ep.temperature, "max_tokens": max_tokens}
        if schema is not None and self.supports_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "record", "strict": True, "schema": schema}}
        with httpx.Client(timeout=self.ep.timeout_s) as c:
            r = c.post(f"{self.base}/chat/completions", json=body, headers=self.headers)
            if r.status_code == 400 and schema is not None and self.supports_schema:
                # Server without schema support: fall back to prompt-only JSON.
                self.supports_schema = False
                body.pop("response_format", None)
                r = c.post(f"{self.base}/chat/completions", json=body, headers=self.headers)
        if r.status_code >= 400:
            raise LLMError(f"{r.status_code}: {r.text[:500]}")
        data = r.json()
        return data["choices"][0]["message"].get("content") or "", data.get("usage", {})

    def structured(self, messages: list[dict[str, Any]], schema: dict[str, Any], retries: int = 1,
                   extra_check=None, max_tokens: int = 900) -> tuple[dict[str, Any], dict[str, Any]]:
        """Ask for JSON matching ``schema``. Malformed or invalid output gets one
        corrective retry with the validation errors; then ValidationFailed."""
        msgs = list(messages)
        last_raw = ""
        usage_total: dict[str, Any] = {"attempts": 0}
        for attempt in range(retries + 1):
            usage_total["attempts"] += 1
            raw, usage = self.chat(msgs, schema, max_tokens)
            for k, v in usage.items():
                if isinstance(v, (int, float)):
                    usage_total[k] = usage_total.get(k, 0) + v
            last_raw = raw
            try:
                obj = _extract_json(raw)
                jsonschema.validate(obj, schema)
                problems = extra_check(obj) if extra_check else []
                if problems:
                    raise jsonschema.ValidationError("; ".join(problems))
                return obj, usage_total
            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                err = e.message if isinstance(e, jsonschema.ValidationError) else f"invalid JSON: {e}"
                if attempt >= retries:
                    raise ValidationFailed(err, last_raw) from e
                msgs = msgs + [{"role": "assistant", "content": raw[:4000]},
                               {"role": "user", "content": f"That output was rejected: {err}. Reply again with ONLY a JSON object that "
                                                           f"matches the schema exactly, using only the allowed values."}]
        raise ValidationFailed("unreachable", last_raw)


def health(ep: ModelEndpoint, timeout: float = 3.0) -> dict[str, Any]:
    if not ep.enabled:
        return {"ok": False, "reason": "not configured"}
    try:
        r = httpx.get(ep.base_url.rstrip("/") + "/models", timeout=timeout)
        return {"ok": r.status_code < 400, "status": r.status_code}
    except httpx.HTTPError as e:
        return {"ok": False, "reason": str(e)}
