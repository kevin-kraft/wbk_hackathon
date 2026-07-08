"""Assemble a `DisassemblyOrchestrator` from either mocks or real clients."""

from __future__ import annotations

import os
from collections.abc import Callable

from . import mocks
from .config import OrchestratorConfig
from .loop import DisassemblyOrchestrator
from .models import LoopEvent


def build_orchestrator(
    config: OrchestratorConfig | None = None,
    *,
    dry_run: bool = False,
    on_event: Callable[[LoopEvent], None] | None = None,
) -> DisassemblyOrchestrator:
    config = config or OrchestratorConfig()

    if dry_run:
        return DisassemblyOrchestrator(
            scene_camera=mocks.MockSceneCamera(),
            perception=mocks.MockPerception(),
            pose=mocks.MockPose(),
            grasp=mocks.MockGraspPlanner(),
            movement=mocks.MockMovement(),
            grip=mocks.MockGrip(),
            inspection_camera=mocks.MockInspectionCamera(),
            damage=mocks.MockDamage(),
            # Plan-driven dry runs exercise the full new path: mock plan +
            # dict-shaped synthesizer output through the validate/execute guardrail.
            plan_provider=mocks.MockPlanProvider(),
            synthesizer=mocks.MockActionSynthesizer(),
            config=config,
            on_event=on_event,
        )

    # Real path — imported lazily so the dry-run/tests never need httpx/cv2/numpy.
    from .clients.cameras import OpenCVInspectionCamera, StaticSceneCamera
    from .clients.http_damage import HttpDamage
    from .clients.http_perception import HttpPerception
    from .clients.http_pose import HttpPose
    from .clients.naive_grasp import NaiveTopDownGrasp

    import json

    movement, grip = _build_robot(config, on_event)

    if config.scene_camera_url:
        # Real Zivid capture service (see scene_camera/); satisfies SceneCamera.
        from .clients.http_scene import HttpSceneCamera

        scene = HttpSceneCamera(config)
    else:
        scene_k = json.loads(os.environ["SCENE_K"]) if os.getenv("SCENE_K") else None
        scene = StaticSceneCamera(
            rgb_path=os.getenv("SCENE_RGB_PATH", "scene_rgb.png"),
            depth_path=os.getenv("SCENE_DEPTH_PATH") or None,
            K=scene_k,  # flat-9 intrinsics; required by the pose stage
        )
    return DisassemblyOrchestrator(
        scene_camera=scene,
        perception=HttpPerception(config),
        pose=HttpPose(config),
        grasp=NaiveTopDownGrasp(config),
        movement=movement,
        grip=grip,
        inspection_camera=OpenCVInspectionCamera(int(os.getenv("INSPECTION_CAM_INDEX", "0"))),
        damage=HttpDamage(config),
        plan_provider=_build_plan_provider(config),
        synthesizer=_build_synthesizer(config),
        config=config,
        on_event=on_event,
    )


def _build_plan_provider(config: OrchestratorConfig):
    """LLM-generated plans when configured, static ERP order otherwise."""
    mode = config.planner_mode
    if mode not in ("auto", "llm", "static"):
        raise ValueError(f"PLANNER_MODE must be auto|llm|static, got {mode!r}")
    if mode == "llm" and not config.openrouter_api_key:
        raise ValueError("PLANNER_MODE=llm requires OPENROUTER_API_KEY")
    if mode in ("auto", "llm") and config.openrouter_api_key:
        from .clients.llm_planner import LlmPlanProvider

        return LlmPlanProvider(config)
    from .clients.erp import StaticPlanProvider

    return StaticPlanProvider(config)


def _build_synthesizer(config: OrchestratorConfig):
    """LLM action synthesis is opt-in (ACTION_SYNTHESIS=llm); default is the
    scripted grasp sequence — identical motion to the original loop."""
    mode = config.action_synthesis
    if mode not in ("scripted", "llm"):
        raise ValueError(f"ACTION_SYNTHESIS must be scripted|llm, got {mode!r}")
    if mode == "llm":
        if not config.openrouter_api_key:
            raise ValueError("ACTION_SYNTHESIS=llm requires OPENROUTER_API_KEY")
        from .clients.llm_actions import LlmActionSynthesizer

        return LlmActionSynthesizer(config)
    return None


def _build_robot(config: OrchestratorConfig, on_event: Callable[[LoopEvent], None] | None):
    """Select the movement + grip backends per `config.robot_target`.

    real → the Jetson arm only.  sim → the simulator only.  both → the arm
    (authoritative) with the simulator mirrored in parallel as a digital twin.
    The loop only sees the MovementClient/GripSensor Protocols, so it is unaware
    which robot(s) it is driving.
    """
    from .clients.http_grip import HttpGrip
    from .clients.http_movement import HttpMovement
    from .clients.sim_movement import IsaacSimMovement, SimGrip
    from .clients.tee_movement import TeeMovement

    target = (config.robot_target or "real").strip().lower()
    if target not in ("real", "sim", "both"):
        raise ValueError(f"ROBOT_TARGET must be real|sim|both, got {target!r}")

    real_move = HttpMovement(config, config.movement_url)
    real_grip = HttpGrip(config, config.grip_url)
    if target == "real":
        return real_move, real_grip

    # sim / both need a simulator URL. The sim speaks the Isaac command bus, so it
    # gets the adapter client (not a plain HttpMovement) — see sim_movement.py.
    if not config.movement_sim_url:
        raise ValueError(f"robot_target={target!r} needs MOVEMENT_SIM_URL (the simulator endpoint)")
    sim_move = IsaacSimMovement(config, config.movement_sim_url)
    # The sim exposes no grip endpoint; assume-grasp unless a grip_sim_url is set.
    sim_grip = HttpGrip(config, config.grip_sim_url) if config.grip_sim_url else SimGrip(config)

    def _note(kind: str, exc: Exception) -> None:
        if on_event:
            on_event(LoopEvent(step=0, state="SIM_WARN",
                               message=f"simulator {kind} error (ignored): {exc}", data={}))

    if target == "sim":
        return sim_move, sim_grip
    # both: real arm authoritative + gates via its grip; sim mirrors for the twin view.
    return TeeMovement(real_move, [sim_move], on_mirror_error=_note), real_grip
