"""Grip sensor client — reads the teammate-owned binary pressure sensor.

Follows the proposed contract in `contracts/grip_api.md`.
"""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig


class HttpGrip:
    """Grip sensor for one robot. `base_url` selects the real gripper
    (`config.grip_url`, default) or the simulator's (`config.grip_sim_url`)."""

    def __init__(self, config: OrchestratorConfig, base_url: str | None = None) -> None:
        self.c = config
        self.base_url = base_url or config.grip_url
        self._http = httpx.Client(timeout=config.http_timeout_s)

    def is_grasped(self) -> bool:
        r = self._http.get(f"{self.base_url}/grip")
        r.raise_for_status()
        d = r.json()
        # Accept either {"grasped": bool} or the raw {"raw": 0|1}.
        return bool(d.get("grasped", d.get("raw", 0)))
