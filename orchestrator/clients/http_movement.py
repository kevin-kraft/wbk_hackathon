"""Arm movement client — talks to the teammate-owned Jetson endpoint.

Follows the proposed contract in `contracts/movement_api.md`; adjust to match
whatever the Jetson team finalizes.
"""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig


class HttpMovement:
    """One movement backend. `base_url` selects which robot it drives — the real
    Jetson arm (`config.movement_url`, the default) or the simulator
    (`config.movement_sim_url`). Both speak the same contract, so the loop is
    agnostic; the factory picks the URL per `robot_target`."""

    def __init__(self, config: OrchestratorConfig, base_url: str | None = None) -> None:
        self.c = config
        self.base_url = base_url or config.movement_url
        self._http = httpx.Client(timeout=config.http_timeout_s)

    def _post(self, path: str, body: dict) -> dict:
        r = self._http.post(f"{self.base_url}{path}", json=body)
        r.raise_for_status()
        return r.json()

    def move_to_pose(self, pose_4x4: list[list[float]]) -> None:
        self._post("/move_to_pose", {"pose": pose_4x4, "frame": "base"})

    def move_named(self, name: str) -> None:
        self._post("/move_named", {"name": name})

    def set_gripper(self, closed: bool, width: float | None = None) -> None:
        self._post("/gripper", {"closed": closed, "width": width})
