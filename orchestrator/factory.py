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
            config=config,
            on_event=on_event,
        )

    # Real path — imported lazily so the dry-run/tests never need httpx/cv2/numpy.
    from .clients.cameras import OpenCVInspectionCamera, StaticSceneCamera
    from .clients.http_damage import HttpDamage
    from .clients.http_grip import HttpGrip
    from .clients.http_movement import HttpMovement
    from .clients.http_perception import HttpPerception
    from .clients.http_pose import HttpPose
    from .clients.naive_grasp import NaiveTopDownGrasp

    import json

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
        movement=HttpMovement(config),
        grip=HttpGrip(config),
        inspection_camera=OpenCVInspectionCamera(int(os.getenv("INSPECTION_CAM_INDEX", "0"))),
        damage=HttpDamage(config),
        config=config,
        on_event=on_event,
    )
