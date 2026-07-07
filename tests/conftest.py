"""Shared pytest bootstrap.

This monorepo is three sibling service dirs (`perception/`, `pose/`, `damage/`),
each with its own import root at *runtime* (see supervisord.conf / Dockerfiles):

  - damage/         is run as the package `damage` (repo root on PYTHONPATH,
                    `damage/__init__.py` exists) -> add the repo root.
  - perception/     is run as `services.<name>` with `perception/` itself as the
                    import root (`uvicorn services.yolo.main:app`, cwd=/app/perception)
                    -> add `perception/`.
  - pose/           is run as top-level `shared` / `foundationpose_svc` /
                    `gigapose_svc` with `pose/` as PYTHONPATH (see the service
                    Dockerfiles: ENV PYTHONPATH=/svc, COPY shared, COPY
                    foundationpose_svc) -> add `pose/`.

None of these three roots collide on a top-level module name, so all three can
be on sys.path at once.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_ROOTS = [
    REPO_ROOT,  # -> `damage`
    REPO_ROOT / "perception",  # -> `services`
    REPO_ROOT / "pose",  # -> `shared`, `foundationpose_svc`, `gigapose_svc`
]

for _root in _ROOTS:
    _root_str = str(_root)
    if _root_str not in sys.path:
        sys.path.insert(0, _root_str)
