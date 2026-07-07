"""Environment-driven configuration for the orchestrator.

Service URLs cover our own stages (perception/pose/damage) plus the two
teammate-owned endpoints (Jetson movement, grip sensor) whose contracts are
proposed in `contracts/`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _identity4x4() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


@dataclass
class OrchestratorConfig:
    # --- our stages ---
    perception_yolo_url: str = field(default_factory=lambda: os.getenv("PERCEPTION_YOLO_URL", "http://localhost:8001"))
    perception_sam3_url: str = field(default_factory=lambda: os.getenv("PERCEPTION_SAM3_URL", "http://localhost:8002"))
    perception_locate_url: str = field(default_factory=lambda: os.getenv("PERCEPTION_LOCATE_URL", "http://localhost:8003"))
    pose_url: str = field(default_factory=lambda: os.getenv("POSE_URL", "http://localhost:8004"))  # foundationpose
    damage_url: str = field(default_factory=lambda: os.getenv("DAMAGE_URL", "http://localhost:8006"))

    # --- teammate-owned endpoints (see contracts/) ---
    movement_url: str = field(default_factory=lambda: os.getenv("MOVEMENT_URL", "http://jetson.local:9000"))
    grip_url: str = field(default_factory=lambda: os.getenv("GRIP_URL", "http://jetson.local:9001"))

    # --- behaviour ---
    next_part_query: str = field(default_factory=lambda: os.getenv("NEXT_PART_QUERY", "the next part to remove to disassemble this object"))
    max_grasp_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_GRASP_ATTEMPTS", "3")))
    max_steps: int = field(default_factory=lambda: int(os.getenv("MAX_STEPS", "50")))
    inspection_angles: int = field(default_factory=lambda: int(os.getenv("INSPECTION_ANGLES", "3")))
    http_timeout_s: float = field(default_factory=lambda: float(os.getenv("ORCH_HTTP_TIMEOUT_S", "120")))

    # camera->base extrinsics for grasp planning (flat 16 row-major JSON); identity default.
    T_base_cam: list[list[float]] = field(
        default_factory=lambda: (
            [row for row in _chunk(json.loads(os.environ["T_BASE_CAM"]), 4)]
            if os.getenv("T_BASE_CAM")
            else _identity4x4()
        )
    )


def _chunk(flat: list[float], n: int) -> list[list[float]]:
    return [flat[i : i + n] for i in range(0, len(flat), n)]
