"""OpenRouter vision call for damage inspection.

Uses the OpenAI-compatible /chat/completions endpoint with image content parts.
Returns the model's raw JSON verdict dict; the app maps it to the response schema.
"""

from __future__ import annotations

import json
import re

import httpx

from .config import Settings


class OpenRouterError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip ```json fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise OpenRouterError(f"Model did not return JSON: {text[:300]!r}")
        return json.loads(m.group(0))


def call_openrouter(settings: Settings, messages: list[dict]) -> dict:
    if not settings.api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not set.")

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "HTTP-Referer": settings.referer,
        "X-Title": settings.app_title,
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=settings.request_timeout_s) as client:
        resp = client.post(
            f"{settings.base_url.rstrip('/')}/chat/completions",
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
