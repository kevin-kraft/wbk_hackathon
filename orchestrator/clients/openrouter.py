"""Minimal OpenRouter chat call for the orchestrator's LLM clients.

Mirrors damage/client.py's pattern (same provider, same env-var family — see
the PRD's provider decision: reuse OpenRouter rather than add a second LLM
provider). Kept local because the orchestrator container doesn't ship damage/,
consistent with the repo's copy-per-service auth.py precedent.
"""

from __future__ import annotations

import json
import re

import httpx

from ..config import OrchestratorConfig


class OpenRouterError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise OpenRouterError(f"Model did not return JSON: {text[:300]!r}")
        return json.loads(m.group(0))


def chat_json(config: OrchestratorConfig, messages: list[dict]) -> dict:
    """One chat completion, temperature 0, JSON response — returns the parsed dict."""
    if not config.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not set.")
    headers = {
        "Authorization": f"Bearer {config.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.planner_model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=config.http_timeout_s) as client:
        resp = client.post(
            f"{config.openrouter_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
    if resp.status_code >= 400:
        raise OpenRouterError(f"OpenRouter {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenRouterError(f"Unexpected OpenRouter response: {data}") from exc
    return _extract_json(content)
