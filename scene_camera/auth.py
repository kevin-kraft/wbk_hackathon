"""Optional shared-token auth (matches the other wbk services).

Set `WBK_API_TOKEN` to require callers to present that token; leave it unset and
auth is disabled. Token rides as `Authorization: Bearer <token>` or `?token=`.
`/health` is left open for monitoring.
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
