"""Shared-token auth on the orchestrator's /run + /events/run.

Token is read from WBK_API_TOKEN at request time (see orchestrator/auth.py):
unset => open; set => Bearer header (or ?token= for the SSE stream) required.
/health stays open. dry_run keeps it mock-only, no services needed.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator import app as orch_app

client = TestClient(orch_app.app)
TOKEN = "s3cret-token"


def test_health_is_open_even_with_token_set(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert client.get("/health").status_code == 200


def test_run_open_when_token_unset(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    r = client.post("/run?dry_run=true")
    assert r.status_code == 200
    assert r.json()["stats"]["removed"] == 3


def test_run_rejects_without_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert client.post("/run?dry_run=true").status_code == 401


def test_run_accepts_correct_bearer(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    r = client.post("/run?dry_run=true", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


def test_run_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    r = client.post("/run?dry_run=true", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_events_run_accepts_query_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    r = client.get(f"/events/run?dry_run=true&delay=0&token={TOKEN}")
    assert r.status_code == 200


def test_events_run_rejects_without_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert client.get("/events/run?dry_run=true&delay=0").status_code == 401
