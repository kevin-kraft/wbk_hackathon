"""Optional shared-token auth.

Set `WBK_API_TOKEN` in the service environment to require callers to present that
token; leave it unset and auth is disabled (dev/CI/mocks keep working). Callers
pass it either as `Authorization: Bearer <token>` or as a `?token=` query param
(the query form is for browser SSE, where headers can't be set). `/health` is
left open so monitoring works without the token.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, Query


def _presented(authorization: str | None, token: str | None) -> str | None:
    if token:
        return token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :].strip()
    return None


def require_token(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    expected = os.getenv("WBK_API_TOKEN")
    if not expected:
        return  # auth disabled
    presented = _presented(authorization, token)
    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API token")
