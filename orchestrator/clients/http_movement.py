"""Arm movement client — talks to the teammate-owned Jetson endpoint.

Follows the proposed contract in `contracts/movement_api.md`; adjust to match
whatever the Jetson team finalizes.
"""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig


class HttpMovement:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.c = config
        self._http = httpx.Client(timeout=config.http_timeout_s)

    def _post(self, path: str, body: dict) -> dict:
        r = self._http.post(f"{self.c.movement_url}{path}", json=body)
        r.raise_for_status()
        return r.json()

    def move_to_pose(self, pose_4x4: list[list[float]]) -> None:
        self._post("/move_to_pose", {"pose": pose_4x4, "frame": "base"})

    def move_named(self, name: str) -> None:
        self._post("/move_named", {"name": name})

    def set_gripper(self, closed: bool, width: float | None = None) -> None:
        self._post("/gripper", {"closed": closed, "width": width})
