"""Plain data structures passed between orchestrator stages.

Dataclasses (not pydantic) so the orchestrator library imports with no heavy
deps and the dry-run / tests run anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2


@dataclass
class SceneFrame:
    """A capture from the scene camera looking at the assembly."""

    rgb_b64: str
    depth_b64: str | None = None  # uint16 mm PNG, for pose
    K: list[float] | None = None  # flat 9 intrinsics


@dataclass
class PartDetection:
    """The next part to remove, as located by perception."""

    class_name: str
    score: float = 1.0
    box: Box | None = None
    point: tuple[float, float] | None = None
    mask_b64: str | None = None
    id: int | str = 0
    # Slot-localization mode only: the slot's pre-measured grasp pose in the base
    # frame (T_base_grasp, 4x4). Set by SlotPerception, consumed by SlotGraspPlanner
    # in place of the pose->back-projection chain. None in the default pose mode.
    slot_pose: list[list[float]] | None = None


@dataclass
class Pose:
    """6DoF pose of the target part (object->camera, 4x4, metres)."""

    T_cam_obj: list[list[float]]
    score: float | None = None
    stage: str | None = None


@dataclass
class Grasp:
    """A grasp to attempt, in the robot base frame."""

    T_base_grasp: list[list[float]]  # 4x4 grasp pose
    pre_grasp: list[list[float]] | None = None  # approach/stand-off pose
    width: float | None = None  # target gripper opening
    meta: dict = field(default_factory=dict)


@dataclass
class Inspection:
    verdict: str  # ok | damaged | uncertain
    damaged: bool
    bin: str  # ok_bin | reject_bin
    confidence: float = 0.0
    issues: list[str] = field(default_factory=list)


@dataclass
class PlanStep:
    """One step of a generated disassembly plan: remove `part` by doing `action`."""

    part: str  # perception class name of the part this step removes
    action: str  # human-readable instruction, e.g. "lift the top cover straight up"
    index: int = 0  # 1-based position in the plan
    notes: str | None = None  # extra ERP context (fasteners, tools, cautions)


@dataclass
class Plan:
    """An ordered disassembly plan for one product (ERP-derived, LLM- or statically generated)."""

    product: str
    steps: list[PlanStep] = field(default_factory=list)
    source: str = "static"  # static | llm | mock | static-fallback
    rationale: str | None = None


@dataclass
class ArmAction:
    """One arm command from the constrained action vocabulary (see actions.py).

    This is the ONLY shape in which an LLM may propose robot motion: named poses
    from a fixed allowlist, or a move to a pipeline-computed pose referenced by
    name (`pose_ref`) — never a free-form matrix. `validate_actions` enforces it
    before anything reaches a MovementClient.
    """

    kind: str  # move_named | move_to_pose | gripper
    name: str | None = None  # for move_named
    pose_ref: str | None = None  # for move_to_pose: pre_grasp | grasp
    closed: bool | None = None  # for gripper
    width: float | None = None  # for gripper (optional; system default if None)


@dataclass
class LoopEvent:
    """One step of the state machine, for logging / the live demo narration."""

    step: int
    state: str
    message: str
    data: dict = field(default_factory=dict)
