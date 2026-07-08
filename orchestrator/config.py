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


# Hand-eye calibration result (eye-to-hand, base<-camera), solved 2026-07-07.
# The calibration output translation was in mm (−174.7977, −55.13062, 1199.66);
# stored here in METRES to match the pose stage. This is the default T_base_cam;
# override via the T_BASE_CAM env var if the arm is re-calibrated (no code change).
_BASE_CAM_CALIBRATED: list[list[float]] = [
    [-0.7971158, -0.488645, 0.3547288, -0.1747977],
    [-0.4955818, 0.8650522, 0.07799571, -0.05513062],
    [-0.3449712, -0.1136255, -0.9317103, 1.19966],
    [0.0, 0.0, 0.0, 1.0],
]


def _load_matrix(
    env_name: str,
    units_env: str | None = None,
    default: list[list[float]] | None = None,
) -> list[list[float]]:
    """Load a 4x4 transform from a flat-16 row-major JSON env var.

    Falls back to `default` when the env var is unset (identity if no default).
    If `units_env` resolves to "mm", the translation column is converted to
    metres — the pose stage emits metres, so a mm extrinsic (e.g. straight from
    Zivid hand-eye calibration) must be scaled before composing with it.
    """
    raw = os.getenv(env_name)
    if not raw:
        return [row[:] for row in default] if default is not None else _identity4x4()
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
    # Scene RGB-D camera (Zivid) capture service. Empty = use the file/static
    # stand-in (StaticSceneCamera) instead of the HTTP client.
    scene_camera_url: str = field(default_factory=lambda: os.getenv("SCENE_CAMERA_URL", ""))

    # --- teammate-owned endpoints (see contracts/) ---
    # The REAL robot on the Jetson.
    movement_url: str = field(default_factory=lambda: os.getenv("MOVEMENT_URL", "http://jetson.local:9000"))
    grip_url: str = field(default_factory=lambda: os.getenv("GRIP_URL", "http://jetson.local:9001"))
    # A SIMULATED robot (digital twin) implementing the same movement contract
    # (contracts/movement_api.md) and, ideally, the grip contract too. Empty until
    # the sim endpoint lands. See contracts/simulation_api.md.
    movement_sim_url: str = field(default_factory=lambda: os.getenv("MOVEMENT_SIM_URL", ""))
    grip_sim_url: str = field(default_factory=lambda: os.getenv("GRIP_SIM_URL", ""))
    # Which robot the loop drives:
    #   "real" — the Jetson arm only (default; unchanged behaviour)
    #   "sim"  — the simulator only (safe dry-motion; no real hardware moves)
    #   "both" — drive BOTH in parallel; the real arm is authoritative (its errors
    #            fail the step + its grip sensor gates), the sim mirrors for a live
    #            digital-twin view and its faults never break a real run.
    # Overridable per-run via the /run?target= query param (no restart needed).
    robot_target: str = field(default_factory=lambda: os.getenv("ROBOT_TARGET", "real").strip().lower())

    # --- planning head (ERP + LLM, see clients/erp.py + clients/llm_planner.py) ---
    # Per-product mock-ERP dataset; defaults to the file packaged with the image.
    erp_products_path: str = field(default_factory=lambda: os.getenv(
        "ERP_PRODUCTS_PATH",
        os.path.join(os.path.dirname(__file__), "data", "erp_products.json"),
    ))
    # How plans are generated for plan-driven runs:
    #   "auto"   — LLM when OPENROUTER_API_KEY is set, else the static ERP order (default)
    #   "llm"    — LLM required (error without a key)
    #   "static" — always the ERP order, never an LLM
    planner_mode: str = field(default_factory=lambda: os.getenv("PLANNER_MODE", "auto").strip().lower())
    # Whether the approach+grasp motion is LLM-proposed ("llm", constrained to the
    # actions.py vocabulary + validated, scripted fallback) or always scripted
    # ("scripted", default — identical to the original loop behaviour).
    action_synthesis: str = field(default_factory=lambda: os.getenv("ACTION_SYNTHESIS", "scripted").strip().lower())
    # Same OpenRouter env-var family the damage stage already uses (reuse, not a
    # second provider). PLANNER_MODEL covers both plan generation + action synthesis.
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    planner_model: str = field(default_factory=lambda: os.getenv("PLANNER_MODEL", "anthropic/claude-sonnet-5"))
    openrouter_base_url: str = field(default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))

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
    # STATIC matrix — never recomposed per frame. Defaults to the calibrated result
    # solved 2026-07-07 (_BASE_CAM_CALIBRATED, in metres). Override via T_BASE_CAM as
    # flat-16 row-major JSON (base<-camera) after a re-calibration; set
    # T_BASE_CAM_UNITS=mm if that output translation is in mm (converted to metres).
    T_base_cam: list[list[float]] = field(
        default_factory=lambda: _load_matrix("T_BASE_CAM", "T_BASE_CAM_UNITS", default=_BASE_CAM_CALIBRATED)
    )
    # Grasp offset in the OBJECT frame (obj->grasp), from CAD / the grasp planner.
    # Full runtime chain: base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp.
    obj_T_grasp: list[list[float]] = field(default_factory=lambda: _load_matrix("T_OBJ_GRASP", "T_OBJ_GRASP_UNITS"))
    # Pre-grasp stand-off distance (metres) along the grasp approach axis.
    grasp_approach_dist: float = field(default_factory=lambda: float(os.getenv("ORCH_APPROACH_DIST", "0.10")))

    @property
    def auth_headers(self) -> dict[str, str]:
        """Bearer header sent to downstream stages when a token is configured."""
        return {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
