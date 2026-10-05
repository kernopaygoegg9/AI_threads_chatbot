"""Claude wrapper: every call returns JSON validated against a schema (structured outputs)."""
from __future__ import annotations

import json
from typing import Any

import anthropic

from . import settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


def _client() -> anthropic.Anthropic:
    key = settings.load_secrets().anthropic_api_key
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def generate_json(system: str, user: str, schema: dict[str, Any], *, max_tokens: int = 16000) -> dict:
    """Run one Claude request with a JSON-schema output format and return the parsed object."""
    cfg = settings.config()["llm"]
    kwargs: dict[str, Any] = {
        "model": cfg["model"],
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": cfg.get("effort", "high"), "format": {"type": "json_schema", "schema": schema}},
    }
    client = _client()
    if cfg.get("refusal_fallback", True):
        # On a safety refusal the API reruns the request on a fallback model chosen by category.
        resp = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
    else:
        resp = client.messages.create(**kwargs)

    if resp.stop_reason == "refusal":
        raise LLMError(f"model refused: {getattr(resp, 'stop_details', None)}")
    if resp.stop_reason == "max_tokens":
        raise LLMError("output truncated at max_tokens")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        raise LLMError("no text block in response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"invalid JSON from model: {text[:200]}") from e


def obj(properties: dict[str, Any]) -> dict[str, Any]:
    """Build a strict JSON-schema object where every property is required."""
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
