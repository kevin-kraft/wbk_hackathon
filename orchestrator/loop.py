"""The disassembly state machine — the project's connective tissue.

Two modes share the same per-part machinery (POSE -> PLAN -> GRASP+VERIFY ->
REMOVE -> confirm removed -> INSPECT -> SORT):

- **Fixed mode** (default, `run()` with no product): perception decides what to
  remove next (`perception.next_part`), looping until nothing remains — the
  original pipeline.
- **Plan mode** (`run(product=...)` with a PlanProvider wired): a generated,
  ordered per-product plan decides what to remove next; perception's job shifts
  to grounding each step's named part in the scene (`perception.locate`) and
  confirming removal. A step that cannot be completed BLOCKS the run (ordered
  disassembly: later parts may be under the stuck one).

The "rectify grabbing mistakes" product goal lives in `_grasp_with_retry`: the
grip sensor gates progress, and a failed read triggers a re-planned retry. When
an ActionSynthesizer is wired, the approach/grasp motion comes from LLM-proposed
actions in the constrained vocabulary (actions.py) — validated deterministically,
with the scripted sequence as fallback on any violation (GUARDRAIL event).
"""

from __future__ import annotations

from collections.abc import Callable

from .actions import (
    ActionValidationError,
    execute_actions,
    scripted_grasp_sequence,
    validate_actions,
)
from .clients.base import (
    ActionSynthesizer,
    DamageClient,
    GraspPlanner,
    GripSensor,
    InspectionCamera,
    MovementClient,
    PerceptionClient,
    PlanProvider,
    PoseClient,
    SceneCamera,
)
from .config import OrchestratorConfig
from .models import Grasp, LoopEvent, PartDetection, PlanStep


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
        plan_provider: PlanProvider | None = None,
        synthesizer: ActionSynthesizer | None = None,
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
        self.plan_provider = plan_provider
        self.synthesizer = synthesizer
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
    def run(self, product: str | None = None) -> dict:
        """Run a disassembly. With `product` (and a PlanProvider wired), the run
        is plan-driven; otherwise perception drives it as before."""
        if product is not None:
            if self.plan_provider is None:
                raise ValueError("plan-driven run requested but no PlanProvider is wired")
            return self._run_planned(product)
        return self._run_fixed()

    # ------------------------------------------------------------------ #
    def _run_fixed(self) -> dict:
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

            outcome = self._process_part(step, frame, part, stats)
            if outcome == "skipped":
                blacklist.add(part.class_name)

        self._emit(step, "SUMMARY", f"finished: {stats}", **stats)
        return stats

    # ------------------------------------------------------------------ #
    def _run_planned(self, product: str) -> dict:
        stats = {"removed": 0, "ok_bin": 0, "reject_bin": 0, "skipped": 0}
        plan = self.plan_provider.get_plan(product)  # type: ignore[union-attr]
        self._emit(
            0, "PLAN_GENERATED",
            f"plan for {plan.product}: {len(plan.steps)} steps (source={plan.source})",
            product=plan.product, source=plan.source, rationale=plan.rationale,
            steps=[{"part": s.part, "action": s.action} for s in plan.steps],
        )

        step = 0  # global step counter — bounds retries the same way fixed mode does
        idx = 0  # position in the plan
        while idx < len(plan.steps) and step < self.config.max_steps:
            step += 1
            plan_step = plan.steps[idx]
            self._emit(step, "STEP",
                       f"plan step {idx + 1}/{len(plan.steps)}: {plan_step.action}",
                       part=plan_step.part, index=idx + 1, total=len(plan.steps),
                       action=plan_step.action)

            frame = self.scene_camera.capture_scene()
            part = self.perception.locate(frame, plan_step.part)
            if part is None:
                # The plan expected the part; scene says it's not there (already
                # removed / never present). Note it and move on — no motion done.
                self._emit(step, "SKIP", f"{plan_step.part} not found in scene — skipping step",
                           part=plan_step.part)
                stats["skipped"] += 1
                idx += 1
                continue
            self._emit(step, "LOCATE", f"located {part.class_name}", part=part.class_name)

            outcome = self._process_part(step, frame, part, stats, plan_step=plan_step)
            if outcome == "removed":
                idx += 1
            elif outcome == "skipped":
                # Ordered disassembly: a step we cannot complete blocks the rest.
                self._emit(step, "BLOCKED",
                           f"plan step {idx + 1} ({plan_step.part}) could not be completed "
                           "— stopping for operator")
                break
            # outcome == "retry": same plan step again, bounded by max_steps
        else:
            if idx >= len(plan.steps):
                self._emit(step, "DONE", f"plan for {plan.product} complete")

        self._emit(step, "SUMMARY", f"finished: {stats}", **stats)
        return stats

    # ------------------------------------------------------------------ #
    def _process_part(
        self,
        step: int,
        frame,
        part: PartDetection,
        stats: dict,
        plan_step: PlanStep | None = None,
    ) -> str:
        """POSE -> PLAN -> GRASP -> REMOVE -> INSPECT -> SORT for one located part.

        Returns "removed" | "skipped" (grasp never confirmed) | "retry" (part
        still present after lift — wrong/failed grab)."""
        part.mask_b64 = self.perception.segment(frame, part) or part.mask_b64
        pose = self.pose.estimate(frame, part)
        self._emit(step, "POSE", f"6DoF pose for {part.class_name}", stage=pose.stage)

        grasp = self.grasp.plan(pose, part)
        if not self._grasp_with_retry(step, grasp, part, plan_step=plan_step):
            self._emit(step, "SKIP", f"could not grasp {part.class_name} after "
                                     f"{self.config.max_grasp_attempts} attempts")
            stats["skipped"] += 1
            self.movement.set_gripper(closed=False)
            self.movement.move_named("home")
            return "skipped"

        self.movement.move_named("clearance")  # lift the part clear of the assembly
        self._emit(step, "REMOVE", f"lifted {part.class_name} clear")

        after = self.scene_camera.capture_scene()
        if self.perception.is_present(after, part):
            # Sensor said gripped, but the part is still in the assembly ->
            # wrong part / slipped. Release and let the caller re-detect + retry.
            self._emit(step, "RECHECK", f"{part.class_name} still present after lift — "
                                        "wrong/failed grab, releasing and retrying")
            self.movement.set_gripper(closed=False)
            self.movement.move_named("home")
            return "retry"
        stats["removed"] += 1

        images = self._present_and_capture()
        inspection = self.damage.inspect(images, part)
        self.movement.move_named(inspection.bin)
        self.movement.set_gripper(closed=False)  # drop into the bin
        self.movement.move_named("home")
        stats[inspection.bin] = stats.get(inspection.bin, 0) + 1
        self._emit(step, "SORT", f"{part.class_name}: {inspection.verdict} -> {inspection.bin}",
                   verdict=inspection.verdict, bin=inspection.bin)
        return "removed"

    # ------------------------------------------------------------------ #
    def _grasp_actions(self, step: int, grasp: Grasp, part: PartDetection,
                       plan_step: PlanStep | None):
        """The approach+grasp motion: LLM-proposed within the constrained
        vocabulary when a synthesizer is wired, scripted otherwise. Any
        synthesis/validation failure falls back to the scripted sequence."""
        if self.synthesizer is not None:
            try:
                proposed = self.synthesizer.synthesize(part, grasp, plan_step)
                return validate_actions(proposed, context="grasp")
            except ActionValidationError as exc:
                self._emit(step, "GUARDRAIL",
                           f"synthesized actions rejected ({exc}) — using scripted grasp",
                           reason=str(exc))
            except Exception as exc:
                self._emit(step, "GUARDRAIL",
                           f"action synthesis failed ({exc}) — using scripted grasp",
                           reason=str(exc))
        return scripted_grasp_sequence(grasp)

    def _grasp_with_retry(self, step: int, grasp: Grasp, part: PartDetection,
                          plan_step: PlanStep | None = None) -> bool:
        """Move to the grasp, close, and verify with the grip sensor. On a
        failed read (sensor=0), re-plan and retry — the rectify behaviour."""
        for attempt in range(1, self.config.max_grasp_attempts + 1):
            actions = self._grasp_actions(step, grasp, part, plan_step)
            execute_actions(actions, self.movement, grasp)

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
