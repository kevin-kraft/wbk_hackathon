"""Stage-client interfaces (Protocols).

The orchestrator depends only on these; real HTTP clients and mocks both satisfy
them. This is what lets us build and demo the full loop while YOLO detection, the
Jetson movement endpoint, and the grip sensor are still being built by teammates
— we run against mocks now and swap in the real clients as they land, no changes
to the state machine.
"""

from __future__ import annotations

from typing import Protocol

from ..models import ArmAction, Grasp, Inspection, PartDetection, Plan, PlanStep, Pose, SceneFrame


class SceneCamera(Protocol):
    def capture_scene(self) -> SceneFrame:
        """RGB(-D) view of the assembly."""


class PerceptionClient(Protocol):
    def next_part(self, frame: SceneFrame) -> PartDetection | None:
        """Locate the next part to remove; None when nothing remains.

        Should be a function of the current scene (stateless), so re-calling it
        after a failed step naturally re-proposes the same part.
        """

    def locate(self, frame: SceneFrame, class_name: str) -> PartDetection | None:
        """Ground a SPECIFIC named part in the scene (plan-driven mode); None if
        it isn't visible. Unlike `next_part`, the part is chosen by the plan,
        not by perception."""

    def segment(self, frame: SceneFrame, part: PartDetection) -> str | None:
        """Precise mask (base64 PNG) of the target part, for pose + before/after."""

    def is_present(self, frame: SceneFrame, part: PartDetection) -> bool:
        """Whether the part is still in the assembly (used to confirm removal)."""


class PlanProvider(Protocol):
    """Head of pipeline: turn an operator-selected product into an ordered
    disassembly plan (ERP data + optionally an LLM — see clients/erp.py and
    clients/llm_planner.py)."""

    def get_plan(self, product_id: str) -> Plan:
        """Ordered steps for disassembling `product_id`. Raises ValueError for
        an unknown product."""


class ActionSynthesizer(Protocol):
    """Proposes arm actions for one plan step, in the constrained vocabulary
    (actions.py). The loop validates the output with `validate_actions` and
    falls back to the scripted sequence on ANY violation — implementations can
    therefore be best-effort."""

    def synthesize(self, part: PartDetection, grasp: Grasp, step: PlanStep | None) -> list[ArmAction]:
        """Action sequence to approach + grasp `part` for this plan step. May
        return raw dicts (e.g. straight from an LLM); the loop coerces them."""


class PoseClient(Protocol):
    def estimate(self, frame: SceneFrame, part: PartDetection) -> Pose:
        """6DoF pose of the target part."""


class GraspPlanner(Protocol):
    def plan(self, pose: Pose, part: PartDetection) -> Grasp:
        """Turn a 6DoF pose into a grasp to attempt."""

    def replan(self, grasp: Grasp, attempt: int) -> Grasp:
        """Adjust the grasp after a failed attempt (the rectify step)."""


class MovementClient(Protocol):
    """Primitives against the Jetson arm endpoint (see contracts/movement_api.md)."""

    def move_to_pose(self, pose_4x4: list[list[float]]) -> None: ...

    def move_named(self, name: str) -> None:
        """Move to a named pose: home | clearance | inspect_0.. | ok_bin | reject_bin."""

    def set_gripper(self, closed: bool, width: float | None = None) -> None: ...


class GripSensor(Protocol):
    def is_grasped(self) -> bool:
        """Binary pressure-sensor read: True = something is gripped (see contracts/grip_api.md)."""


class InspectionCamera(Protocol):
    def capture(self) -> str:
        """One base64 image from the inspection webcam (arm holds the part to it)."""


class DamageClient(Protocol):
    def inspect(self, images_b64: list[str], part: PartDetection) -> Inspection:
        """OK/damaged verdict + target bin for a removed part."""
