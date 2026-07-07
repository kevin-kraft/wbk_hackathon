"""damage/client.py — _extract_json() and call_openrouter() error handling."""

from __future__ import annotations

import pytest

from damage.client import OpenRouterError, _extract_json, call_openrouter
from damage.config import Settings


def test_extract_json_plain():
    text = '{"verdict": "ok", "confidence": 0.9}'
    assert _extract_json(text) == {"verdict": "ok", "confidence": 0.9}


def test_extract_json_fenced_with_json_tag():
    text = '```json\n{"verdict": "damaged"}\n```'
    assert _extract_json(text) == {"verdict": "damaged"}


def test_extract_json_fenced_without_json_tag():
    text = '```\n{"verdict": "damaged"}\n```'
    assert _extract_json(text) == {"verdict": "damaged"}


def test_extract_json_embedded_in_prose():
    text = 'Sure, here is my assessment:\n{"verdict": "uncertain", "confidence": 0.4}\nHope that helps!'
    assert _extract_json(text) == {"verdict": "uncertain", "confidence": 0.4}


def test_extract_json_raises_on_no_json():
    with pytest.raises(OpenRouterError):
        _extract_json("I refuse to answer in JSON.")


def test_call_openrouter_raises_without_api_key():
    settings = Settings(api_key="")
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        call_openrouter(settings, messages=[])
