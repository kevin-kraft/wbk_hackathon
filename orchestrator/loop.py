"""The disassembly state machine — the project's connective tissue.

Per part:  LOCATE (perception) -> POSE (6DoF) -> PLAN (grasp) -> GRASP+VERIFY
(move + pressure sensor, with rectify-retry) -> REMOVE -> confirm removed
-> INSPECT (multi-angle webcam -> damage VLM) -> SORT into ok_bin / reject_bin.
Loop until perception reports nothing left.

The "rectify grabbing mistakes" product goal lives in `_grasp_with_retry`: the
binary grip sensor gates progress, and a failed read triggers a re-planned retry.
"""

from __future__ import annotations

from collections.abc import Callable

from .clients.base import (
    DamageClient,
    GraspPlanner,
    GripSensor,
    InspectionCamera,
    MovementClient,
    PerceptionClient,
    PoseClient,
    SceneCamera,
)
from .config import OrchestratorConfig
from .models import Grasp, LoopEvent, PartDetection


class DisassemblyOrchestrator:
    def __init__(
        self,
        *,
        scene_camera: SceneCamera,
        perception: PerceptionClient,
        pose: PoseClient,
        grasp: GraspPlanner,
        movement: MovementClient,
        grip: GripSensor,
        inspection_camera: InspectionCamera,
        damage: DamageClient,
        config: OrchestratorConfig | None = None,
        on_event: Callable[[LoopEvent], None] | None = None,
    ) -> None:
        self.scene_camera = scene_camera
        self.perception = perception
        self.pose = pose
        self.grasp = grasp
        self.movement = movement
        self.grip = grip
        self.inspection_camera = inspection_camera
        self.damage = damage
        self.config = config or OrchestratorConfig()
        self.on_event = on_event
        self.events: list[LoopEvent] = []

    # ------------------------------------------------------------------ #
    def _emit(self, step: int, state: str, message: str, **data) -> None:
        event = LoopEvent(step=step, state=state, message=message, data=data)
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    # ------------------------------------------------------------------ #
    def run(self) -> dict:
        stats = {"removed": 0, "ok_bin": 0, "reject_bin": 0, "skipped": 0}
        blacklist: set[str] = set()  # parts we failed to grasp; stop if one blocks us
        step = 0

        for step in range(1, self.config.max_steps + 1):
            frame = self.scene_camera.capture_scene()

            part = self.perception.next_part(frame)
            if part is None:
                self._emit(step, "DONE", "assembly fully disassembled")
                break
            if part.class_name in blacklist:
                # next_part keeps proposing a part we can't grasp -> can't progress.
                self._emit(step, "BLOCKED", f"{part.class_name} cannot be grasped and "
                                            "blocks progress — stopping for operator")
                break
            self._emit(step, "LOCATE", f"next part: {part.class_name}", part=part.class_name)

            part.mask_b64 = self.perception.segment(frame, part) or part.mask_b64
            pose = self.pose.estimate(frame, part)
            self._emit(step, "POSE", f"6DoF pose for {part.class_name}", stage=pose.stage)

            grasp = self.grasp.plan(pose, part)
            if not self._grasp_with_retry(step, grasp, part):
                self._emit(step, "SKIP", f"could not grasp {part.class_name} after "
                                         f"{self.config.max_grasp_attempts} attempts")
                stats["skipped"] += 1
                blacklist.add(part.class_name)
                self.movement.set_gripper(closed=False)
                self.movement.move_named("home")
                continue

            self.movement.move_named("clearance")  # lift the part clear of the assembly
            self._emit(step, "REMOVE", f"lifted {part.class_name} clear")

            after = self.scene_camera.capture_scene()
            if self.perception.is_present(after, part):
                # Sensor said gripped, but the part is still in the assembly ->
                # wrong part / slipped. Release and let the loop re-detect + retry.
                self._emit(step, "RECHECK", f"{part.class_name} still present after lift — "
                                            "wrong/failed grab, releasing and retrying")
                self.movement.set_gripper(closed=False)
                self.movement.move_named("home")
                continue
            stats["removed"] += 1

            images = self._present_and_capture()
            inspection = self.damage.inspect(images, part)
            self.movement.move_named(inspection.bin)
            self.movement.set_gripper(closed=False)  # drop into the bin
            self.movement.move_named("home")
            stats[inspection.bin] = stats.get(inspection.bin, 0) + 1
            self._emit(step, "SORT", f"{part.class_name}: {inspection.verdict} -> {inspection.bin}",
                       verdict=inspection.verdict, bin=inspection.bin)

        self._emit(step, "SUMMARY", f"finished: {stats}", **stats)
        return stats

    # ------------------------------------------------------------------ #
    def _grasp_with_retry(self, step: int, grasp: Grasp, part: PartDetection) -> bool:
        """Move to the grasp, close, and verify with the pressure sensor. On a
        failed read (sensor=0), re-plan and retry — the rectify behaviour."""
        for attempt in range(1, self.config.max_grasp_attempts + 1):
            if grasp.pre_grasp is not None:
                self.movement.move_to_pose(grasp.pre_grasp)
            self.movement.move_to_pose(grasp.T_base_grasp)
            self.movement.set_gripper(closed=True, width=grasp.width)

            if self.grip.is_grasped():
                self._emit(step, "GRIP", f"grasp confirmed (sensor=1) on attempt {attempt}")
                return True

            self._emit(step, "REGRASP", f"grasp attempt {attempt} failed (sensor=0), re-planning",
                       attempt=attempt)
            self.movement.set_gripper(closed=False)
            grasp = self.grasp.replan(grasp, attempt)
        return False

    def _present_and_capture(self) -> list[str]:
        """Hold the part to the inspection webcam from several angles."""
        images: list[str] = []
        for i in range(self.config.inspection_angles):
            self.movement.move_named(f"inspect_{i}")
            images.append(self.inspection_camera.capture())
        return images
