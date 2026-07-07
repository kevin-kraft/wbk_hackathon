"""Shared-token auth on the damage service's /inspect (the money endpoint).

call_openrouter is monkeypatched so no network/key is needed; we only assert the
auth gate. /health stays open.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from damage import app as damage_app_module

client = TestClient(damage_app_module.app)
TOKEN = "s3cret-token"


def _canned(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"verdict": "ok", "confidence": 0.9, "reasoning": "x"},
    )


def test_health_open(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert client.get("/health").status_code == 200


def test_inspect_open_when_unset(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    _canned(monkeypatch)
    assert client.post("/inspect", json={"images_b64": ["a"]}).status_code == 200


def test_inspect_rejects_without_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _canned(monkeypatch)
    assert client.post("/inspect", json={"images_b64": ["a"]}).status_code == 401


def test_inspect_accepts_bearer(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _canned(monkeypatch)
    r = client.post("/inspect", json={"images_b64": ["a"]}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
