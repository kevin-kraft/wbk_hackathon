"""Environment-driven configuration for the orchestrator.

Service URLs cover our own stages (perception/pose/damage) plus the two
teammate-owned endpoints (Jetson movement, grip sensor) whose contracts are
proposed in `contracts/`. Also holds the hand-eye calibration + grasp geometry.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _identity4x4() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def _load_matrix(env_name: str, units_env: str | None = None) -> list[list[float]]:
    """Load a 4x4 transform from a flat-16 row-major JSON env var (identity if unset).

    If `units_env` resolves to "mm", the translation column is converted to
    metres — the pose stage emits metres, so a mm extrinsic (e.g. straight from
    Zivid hand-eye calibration) must be scaled before composing with it.
    """
    raw = os.getenv(env_name)
    if not raw:
        return _identity4x4()
    flat = [float(x) for x in json.loads(raw)]
    if len(flat) != 16:
        raise ValueError(f"{env_name} must be 16 numbers (flat 4x4 row-major), got {len(flat)}")
    matrix = [flat[i : i + 4] for i in range(0, 16, 4)]
    if units_env and os.getenv(units_env, "m").lower() == "mm":
        for r in range(3):
            matrix[r][3] /= 1000.0
    return matrix


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

    # Shared-token auth (see auth.py). Same token the orchestrator both REQUIRES on
    # its own /run + /events/run and SENDS to perception/pose/damage. Empty = off.
    api_token: str = field(default_factory=lambda: os.getenv("WBK_API_TOKEN", ""))

    # --- hand-eye calibration + grasp geometry ---
    # base<-camera extrinsics: eye-to-hand (camera fixed to the world), so a single
    # STATIC matrix — never recomposed per frame. Supply via T_BASE_CAM as flat-16
    # row-major JSON (base<-camera). Set T_BASE_CAM_UNITS=mm if the calibration
    # output translation is in mm (e.g. Zivid); it is converted to metres.
    # Provided after calibration; identity is a placeholder that makes grasps wrong.
    T_base_cam: list[list[float]] = field(default_factory=lambda: _load_matrix("T_BASE_CAM", "T_BASE_CAM_UNITS"))
    # Grasp offset in the OBJECT frame (obj->grasp), from CAD / the grasp planner.
    # Full runtime chain: base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp.
    obj_T_grasp: list[list[float]] = field(default_factory=lambda: _load_matrix("T_OBJ_GRASP", "T_OBJ_GRASP_UNITS"))
    # Pre-grasp stand-off distance (metres) along the grasp approach axis.
    grasp_approach_dist: float = field(default_factory=lambda: float(os.getenv("ORCH_APPROACH_DIST", "0.10")))

    @property
    def auth_headers(self) -> dict[str, str]:
        """Bearer header sent to downstream stages when a token is configured."""
        return {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
