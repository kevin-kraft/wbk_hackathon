"""Unit tests for robot_control's require_token (app/auth.py).

Same optional shared-token dependency as the other services (see
orchestrator/auth.py, damage/auth.py, perception/services/shared/auth.py,
pose/shared/auth.py): unset WBK_API_TOKEN disables auth entirely; set it and
callers must present a matching token via `Authorization: Bearer <token>` or
`?token=`, else a 401 is raised. Called directly here (not through FastAPI DI)
since require_token is a plain function once the Header/Query defaults are
bypassed by explicit args.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import require_token

TOKEN = "s3cret-token"


def test_auth_disabled_when_token_unset(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    assert require_token(authorization=None, token=None) is None


def test_auth_disabled_ignores_presented_credentials(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    assert require_token(authorization="Bearer whatever", token="whatever") is None


def test_missing_credentials_rejected_when_token_set(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    with pytest.raises(HTTPException) as exc_info:
        require_token(authorization=None, token=None)
    assert exc_info.value.status_code == 401


def test_wrong_bearer_token_rejected(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    with pytest.raises(HTTPException) as exc_info:
        require_token(authorization="Bearer nope", token=None)
    assert exc_info.value.status_code == 401


def test_correct_bearer_token_accepted(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert require_token(authorization=f"Bearer {TOKEN}", token=None) is None


def test_bearer_prefix_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert require_token(authorization=f"bearer {TOKEN}", token=None) is None


def test_correct_query_token_accepted(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert require_token(authorization=None, token=TOKEN) is None


def test_wrong_query_token_rejected(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    with pytest.raises(HTTPException) as exc_info:
        require_token(authorization=None, token="nope")
    assert exc_info.value.status_code == 401


def test_query_token_takes_precedence_over_bearer(monkeypatch):
    # _presented() checks `token` first; a correct query token should win even
    # if a bogus bearer header is also present.
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert require_token(authorization="Bearer nope", token=TOKEN) is None
