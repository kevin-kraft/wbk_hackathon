"""Mock stage-clients — stand-ins for the pieces still being built (YOLO
detection, the Jetson movement endpoint, the grip sensor) plus our own stages,
so the full loop runs end-to-end with no services or hardware.

Parameterized so tests can drive specific scenarios (a failed first grasp to
exercise rectify; a damaged part to exercise the reject bin).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Box, Grasp, Inspection, PartDetection, Plan, PlanStep, Pose, SceneFrame

_DUMMY_IMG = "iVBORw0KGgo="  # placeholder base64; mocks never decode it


def _identity4x4() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class MockSceneCamera:
    def capture_scene(self) -> SceneFrame:
        return SceneFrame(rgb_b64=_DUMMY_IMG, depth_b64=_DUMMY_IMG, K=[600, 0, 320, 0, 600, 240, 0, 0, 1])


class MockPerception:
    """Reveals a fixed sequence of parts, one removed per successful step.

    `next_part` returns the current front of the queue (stateless w.r.t. the
    frame, like real perception would be); a part is only consumed once the loop
    reports it removed via `is_present`.
    """

    def __init__(self, parts: list[str] | None = None) -> None:
        self.remaining = list(parts or ["cover", "bracket", "gear"])

    def next_part(self, frame: SceneFrame) -> PartDetection | None:
        if not self.remaining:
            return None
        name = self.remaining[0]
        return PartDetection(class_name=name, score=0.9, box=Box(100, 100, 200, 200),
                             point=(150, 150), id=name)

    def locate(self, frame: SceneFrame, class_name: str) -> PartDetection | None:
        # Plan-driven grounding: the named part is visible iff not yet removed.
        if class_name not in self.remaining:
            return None
        return PartDetection(class_name=class_name, score=0.9, box=Box(100, 100, 200, 200),
                             point=(150, 150), id=class_name)

    def segment(self, frame: SceneFrame, part: PartDetection) -> str | None:
        return _DUMMY_IMG

    def is_present(self, frame: SceneFrame, part: PartDetection) -> bool:
        # First check after a lift => the part came out; consume it and report absent.
        if self.remaining and self.remaining[0] == part.class_name:
            self.remaining.pop(0)
            return False
        return False


class MockPose:
    def estimate(self, frame: SceneFrame, part: PartDetection) -> Pose:
        return Pose(T_cam_obj=_identity4x4(), score=0.8, stage="refined")


class MockGraspPlanner:
    def plan(self, pose: Pose, part: PartDetection) -> Grasp:
        return Grasp(T_base_grasp=_identity4x4(), pre_grasp=_identity4x4(), width=0.04,
                     meta={"attempt": 0})

    def replan(self, grasp: Grasp, attempt: int) -> Grasp:
        return Grasp(T_base_grasp=grasp.T_base_grasp, pre_grasp=grasp.pre_grasp,
                     width=(grasp.width or 0.04) * 0.9, meta={"attempt": attempt})


@dataclass
class MockMovement:
    calls: list[tuple] = field(default_factory=list)

    def move_to_pose(self, pose_4x4) -> None:
        self.calls.append(("move_to_pose",))

    def move_named(self, name: str) -> None:
        self.calls.append(("move_named", name))

    def set_gripper(self, closed: bool, width: float | None = None) -> None:
        self.calls.append(("set_gripper", closed))


class MockGrip:
    """Binary grip sensor. `fail_first` makes the very first read return 0 (no
    grasp) to exercise the rectify-retry path, then succeeds thereafter."""

    def __init__(self, fail_first: bool = True, always_fail: bool = False) -> None:
        self.always_fail = always_fail
        self._pending_fail = fail_first
        self.reads = 0

    def is_grasped(self) -> bool:
        self.reads += 1
        if self.always_fail:
            return False
        if self._pending_fail:
            self._pending_fail = False
            return False
        return True


class MockPlanProvider:
    """Fixed plan matching MockPerception's default part sequence, so the
    plan-driven loop dry-runs end-to-end with no ERP file or LLM."""

    def __init__(self, steps: list[tuple[str, str]] | None = None) -> None:
        self.step_specs = steps or [
            ("cover", "lift the top cover straight up"),
            ("bracket", "slide the bracket out sideways"),
            ("gear", "pull the gear off its shaft"),
        ]

    def get_plan(self, product_id: str) -> Plan:
        return Plan(
            product=product_id,
            steps=[PlanStep(part=p, action=a, index=i + 1)
                   for i, (p, a) in enumerate(self.step_specs)],
            source="mock",
        )


class MockActionSynthesizer:
    """Returns the canonical grasp vocabulary sequence (as raw dicts, like an
    LLM would) so dry runs exercise the validate->execute guardrail path.
    `bad` makes it emit an out-of-vocabulary action to exercise the fallback."""

    def __init__(self, bad: bool = False) -> None:
        self.bad = bad
        self.calls = 0

    def synthesize(self, part: PartDetection, grasp: Grasp, step: PlanStep | None) -> list:
        self.calls += 1
        if self.bad:
            return [{"kind": "move_to_pose", "pose": [[1, 0, 0, 0]]}]  # coordinates -> rejected
        return [
            {"kind": "move_to_pose", "pose_ref": "pre_grasp"},
            {"kind": "move_to_pose", "pose_ref": "grasp"},
            {"kind": "gripper", "closed": True},
        ]


class MockInspectionCamera:
    def capture(self) -> str:
        return _DUMMY_IMG


class MockDamage:
    """Marks configured part classes as damaged -> reject_bin, else ok -> ok_bin."""

    def __init__(self, damaged_classes: set[str] | None = None) -> None:
        self.damaged_classes = damaged_classes if damaged_classes is not None else {"gear"}

    def inspect(self, images_b64: list[str], part: PartDetection) -> Inspection:
        damaged = part.class_name in self.damaged_classes
        return Inspection(
            verdict="damaged" if damaged else "ok",
            damaged=damaged,
            bin="reject_bin" if damaged else "ok_bin",
            confidence=0.9,
            issues=["crack"] if damaged else [],
        )
