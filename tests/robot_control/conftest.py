"""robot_control test bootstrap.

Importing `app.main` (needed for the FastAPI wiring tests) transitively pulls
in two runtime-only dependencies that are deliberately *not* part of this
repo's light `dev` test dependency group (pyproject.toml) and that this test
suite never actually exercises:

  - `uvicorn` — `app/main.py` does an unconditional top-level `import
    uvicorn`, even though it's only used inside the `if __name__ ==
    "__main__":` block. This is a real inconsistency vs. every other service
    in the repo (orchestrator/app.py, damage/app.py, the perception/pose
    FastAPI modules never import their server package at module scope, since
    they're started via the `uvicorn ...:app` CLI). Flagged, not fixed here
    (out of test-agent scope) — the fix would be moving the import inside the
    `__main__` guard.
  - `requests` — `app/services/pose_client.py` uses it for real, synchronous
    HTTP calls to the external KIP pose API. That's legitimate (unlike
    uvicorn above) but per this task's constraints we don't test network
    calls, so the real package doesn't need to be installed either.

Stub both in sys.modules before any test imports `app.main`; nothing in this
suite calls `uvicorn.run()` or `pose_client.infer_image()`.
"""

from __future__ import annotations

import sys
import types

if "uvicorn" not in sys.modules:
    _uvicorn_stub = types.ModuleType("uvicorn")
    _uvicorn_stub.run = lambda *args, **kwargs: None
    sys.modules["uvicorn"] = _uvicorn_stub

if "requests" not in sys.modules:
    _requests_stub = types.ModuleType("requests")
    _requests_stub.post = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("requests is stubbed in tests; pose_client network calls are out of scope")
    )
    _requests_stub.get = _requests_stub.post
    sys.modules["requests"] = _requests_stub
