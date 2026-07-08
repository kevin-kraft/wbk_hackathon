"""Constrained arm-action vocabulary — the guardrail between LLM output and the robot.

The LLM command synthesizer (clients/llm_actions.py) is an action *selector*, not
a command *generator*: it may only pick from the small vocabulary below, and every
pose it can reference (`pre_grasp`, `grasp`) is computed by the pipeline
(pose stage + grasp chain), never authored by the model. `validate_actions`
deterministically rejects anything outside the vocabulary BEFORE it reaches a
MovementClient; on rejection the loop falls back to the scripted sequence.
robot_control/'s server-side workspace/velocity gates remain the independent
second safety layer. See ADR 0011.

No deps beyond the standard library, so dry-run/tests import this anywhere.
"""

from __future__ import annotations

import re

from .clients.base import MovementClient
from .models import ArmAction, Grasp

# Named poses the arm may be sent to, mirroring contracts/movement_api.md.
STATIC_NAMED_POSES = {"home", "clearance", "ok_bin", "reject_bin"}
_INSPECT_POSE = re.compile(r"^inspect_\d+$")

# Pipeline-computed poses an action may reference. The matrices themselves come
# from the Grasp object at execution time — an action can only NAME them.
POSE_REFS = {"pre_grasp", "grasp"}

ACTION_KINDS = {"move_named", "move_to_pose", "gripper"}

# Bounds: a grasp approach is a handful of motions; anything longer is malformed.
MAX_ACTIONS = 8
MAX_GRIPPER_WIDTH_M = 0.20

# Rendered into the synthesizer LLM's prompt as the *entire* command surface.
VOCABULARY_DOC = """Available actions (JSON objects, executed in order):
- {"kind": "move_to_pose", "pose_ref": "pre_grasp"} — move to the computed stand-off pose
- {"kind": "move_to_pose", "pose_ref": "grasp"} — move to the computed grasp pose
- {"kind": "move_named", "name": "home" | "clearance"} — move to a fixed named pose
- {"kind": "gripper", "closed": true | false} — close/open the gripper
Rules: at most 8 actions; the sequence MUST end with {"kind": "gripper", "closed": true};
poses are computed by the system — you can only reference them by pose_ref, never
emit coordinates. Any other field or value is rejected and a scripted fallback runs."""


class ActionValidationError(ValueError):
    """A proposed action sequence violates the vocabulary — nothing was executed."""


def _coerce(raw: object, i: int) -> ArmAction:
    if isinstance(raw, ArmAction):
        return raw
    if not isinstance(raw, dict):
        raise ActionValidationError(f"action {i}: not an object")
    allowed_keys = {"kind", "name", "pose_ref", "closed", "width"}
    unknown = set(raw) - allowed_keys
    if unknown:
        raise ActionValidationError(f"action {i}: unknown fields {sorted(unknown)}")
    return ArmAction(
        kind=raw.get("kind", ""),
        name=raw.get("name"),
        pose_ref=raw.get("pose_ref"),
        closed=raw.get("closed"),
        width=raw.get("width"),
    )


def validate_actions(
    proposed: list, *, context: str = "grasp", allowed_named: set[str] | None = None
) -> list[ArmAction]:
    """Validate a proposed action sequence against the vocabulary; raise on ANY violation.

    `context="grasp"` (the only context today) additionally requires the sequence
    to end with a single gripper-close — that is the semantic of the grasp step,
    and it is what the grip-sensor check that follows is verifying.
    """
    if not isinstance(proposed, list) or not proposed:
        raise ActionValidationError("empty or non-list action sequence")
    if len(proposed) > MAX_ACTIONS:
        raise ActionValidationError(f"too many actions ({len(proposed)} > {MAX_ACTIONS})")

    named_ok = allowed_named if allowed_named is not None else {"home", "clearance"}
    actions: list[ArmAction] = []
    closes = 0
    for i, raw in enumerate(proposed):
        a = _coerce(raw, i)
        if a.kind not in ACTION_KINDS:
            raise ActionValidationError(f"action {i}: unknown kind {a.kind!r}")
        if a.kind == "move_named":
            in_universe = bool(a.name) and (
                a.name in STATIC_NAMED_POSES or bool(_INSPECT_POSE.match(a.name))
            )
            if not in_universe or a.name not in named_ok:
                raise ActionValidationError(f"action {i}: named pose {a.name!r} not allowed here")
            if a.pose_ref or a.closed is not None or a.width is not None:
                raise ActionValidationError(f"action {i}: stray fields on move_named")
        elif a.kind == "move_to_pose":
            if a.pose_ref not in POSE_REFS:
                raise ActionValidationError(
                    f"action {i}: pose_ref must be one of {sorted(POSE_REFS)}, got {a.pose_ref!r}"
                )
            if a.name or a.closed is not None or a.width is not None:
                raise ActionValidationError(f"action {i}: stray fields on move_to_pose")
        else:  # gripper
            if not isinstance(a.closed, bool):
                raise ActionValidationError(f"action {i}: gripper needs boolean 'closed'")
            if a.width is not None and not (0.0 < float(a.width) <= MAX_GRIPPER_WIDTH_M):
                raise ActionValidationError(f"action {i}: gripper width {a.width!r} out of range")
            if a.name or a.pose_ref:
                raise ActionValidationError(f"action {i}: stray fields on gripper")
            if a.closed:
                closes += 1
        actions.append(a)

    if context == "grasp":
        last = actions[-1]
        if closes != 1 or last.kind != "gripper" or last.closed is not True:
            raise ActionValidationError(
                "grasp sequence must end with exactly one gripper close"
            )
    return actions


def scripted_grasp_sequence(grasp: Grasp) -> list[ArmAction]:
    """The deterministic default: exactly the motion the loop always performed."""
    actions: list[ArmAction] = []
    if grasp.pre_grasp is not None:
        actions.append(ArmAction(kind="move_to_pose", pose_ref="pre_grasp"))
    actions.append(ArmAction(kind="move_to_pose", pose_ref="grasp"))
    actions.append(ArmAction(kind="gripper", closed=True, width=grasp.width))
    return actions


def execute_actions(actions: list[ArmAction], movement: MovementClient, grasp: Grasp) -> None:
    """Run a VALIDATED sequence against the movement client, resolving pose_refs
    from the pipeline-computed grasp. Call `validate_actions` first — this
    function assumes the vocabulary invariants hold."""
    for a in actions:
        if a.kind == "move_named":
            movement.move_named(a.name)  # type: ignore[arg-type]
        elif a.kind == "move_to_pose":
            pose = grasp.pre_grasp if a.pose_ref == "pre_grasp" else grasp.T_base_grasp
            if pose is None:  # pre_grasp referenced but not computed — skip, like the loop did
                continue
            movement.move_to_pose(pose)
        else:
            movement.set_gripper(closed=bool(a.closed), width=a.width if a.width is not None else grasp.width)
