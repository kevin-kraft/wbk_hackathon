from __future__ import annotations

from typing import Any

import numpy as np

from app import env
from app.services import calibration as cal
from app.services import pose_client
from app.services import robot_control
from app.services.transform import absolute_world, apply_transform


def _gate(name: str, ok: bool, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "message": message,
        "details": details or {},
    }


def _in_world_box(xy) -> bool:
    (x_lo, x_hi), (y_lo, y_hi) = env.WORKSPACE_BOX
    return bool(x_lo <= xy[0] <= x_hi and y_lo <= xy[1] <= y_hi)


async def plan_hover(
    *,
    pose_result: dict | None = None,
    image_path: str | None = None,
    part: str | None = None,
    instance_id: int | None = None,
    min_conf: float | None = None,
    calibration_path=None,
    hover_clearance: float | None = None,
    hover_z_abs: float | None = None,
    require_current_tcp: bool = True,
) -> dict[str, Any]:
    if pose_result is None:
        if image_path is None:
            raise ValueError("provide pose_result or image_path")
        pose_result = pose_client.infer_image(image_path)

    min_conf = env.MIN_CONFIDENCE if min_conf is None else min_conf
    hover_clearance = env.HOVER_CLEARANCE_M if hover_clearance is None else hover_clearance
    gates = []

    selected = pose_client.select_instance(
        pose_result,
        part=part,
        instance_id=instance_id,
        min_conf=min_conf,
    )
    table_origin = pose_result["meta"]["table_origin"]
    p_world = absolute_world(selected["t_world"], table_origin)
    gates.append(
        _gate(
            "A",
            True,
            "confidence accepted",
            {"confidence": selected["confidence"], "min_confidence": min_conf},
        )
    )

    world_ok = _in_world_box(p_world[:2])
    gates.append(
        _gate(
            "B",
            world_ok,
            "world XY inside workspace box" if world_ok else "world XY outside workspace box",
            {"p_world": p_world.tolist(), "workspace_box": env.WORKSPACE_BOX},
        )
    )
    if not world_ok:
        return _plan_response(False, gates, selected, p_world.tolist())

    calibration = cal.load_calibration(calibration_path)
    try:
        cal.validate_calibration(calibration)
        calib_ok = calibration.get("tool_down_rpy") is not None
        calib_message = "calibration accepted" if calib_ok else "calibration has no tool_down_rpy"
    except ValueError as exc:
        calib_ok = False
        calib_message = str(exc)
    gates.append(
        _gate(
            "C",
            calib_ok,
            calib_message,
            {
                "residual_rms_m": calibration.get("residual_rms_m"),
                "residual_max_m": calibration.get("residual_max_m"),
            },
        )
    )
    if not calib_ok:
        return _plan_response(False, gates, selected, p_world.tolist())

    rotation = np.array(calibration["R_base_world"]).reshape(3, 3)
    translation = np.array(calibration["t_base_world"])
    p_base = apply_transform(rotation, translation, p_world)
    target_z = hover_z_abs if hover_z_abs is not None else float(p_base[2] + hover_clearance)
    target = [float(p_base[0]), float(p_base[1]), float(target_z), *calibration["tool_down_rpy"]]

    base_ok = cal.in_workspace_base_box(calibration, target[:3])
    gates.append(
        _gate(
            "D",
            base_ok,
            "target inside base workspace box" if base_ok else "target outside base workspace box",
            {"target_xyz": target[:3], "workspace_base_box": calibration["workspace_base_box"]},
        )
    )
    if not base_ok:
        return _plan_response(False, gates, selected, p_world.tolist(), p_base.tolist(), target)

    current_tcp = None
    safe_target = None
    if require_current_tcp:
        current_tcp = await robot_control.get_tcp_pose()
        jump = float(np.linalg.norm(np.array(target[:3]) - np.array(current_tcp[:3])))
        jump_ok = jump <= env.MAX_TCP_JUMP_M
        gates.append(
            _gate(
                "F",
                jump_ok,
                "TCP jump within limit" if jump_ok else "TCP jump exceeds limit",
                {"jump_m": jump, "max_tcp_jump_m": env.MAX_TCP_JUMP_M, "current_tcp": current_tcp},
            )
        )
        if not jump_ok:
            return _plan_response(False, gates, selected, p_world.tolist(), p_base.tolist(), target, current_tcp)
        safe_target = list(current_tcp)
        safe_target[2] = max(float(current_tcp[2]), float(target[2])) + 0.02

    return _plan_response(True, gates, selected, p_world.tolist(), p_base.tolist(), target, current_tcp, safe_target)


async def execute_hover(**kwargs) -> dict[str, Any]:
    confirmation = kwargs.pop("confirmation", None)
    speed = kwargs.pop("speed", None)
    if confirmation != "yes":
        return {
            "status": "rejected",
            "error": "confirmation must be exactly 'yes'",
            "plan": None,
            "moves": [],
        }

    async with robot_control.motion_lock:
        plan = await plan_hover(require_current_tcp=True, **kwargs)
        if plan["status"] != "ok":
            return {"status": "rejected", "error": "hover plan failed safety gates", "plan": plan, "moves": []}

        moves = []
        safe_target = plan.get("safe_target")
        if safe_target is not None:
            moves.append(await robot_control.move_linear(safe_target, speed=speed))
        moves.append(await robot_control.move_linear(plan["target"], speed=speed))
        final_tcp = await robot_control.get_tcp_pose()
        return {"status": "ok", "plan": plan, "moves": moves, "final_tcp": final_tcp}


def _plan_response(
    ok: bool,
    gates: list[dict[str, Any]],
    selected: dict[str, Any],
    p_world: list[float],
    p_base: list[float] | None = None,
    target: list[float] | None = None,
    current_tcp: list[float] | None = None,
    safe_target: list[float] | None = None,
) -> dict[str, Any]:
    return {
        "status": "ok" if ok else "rejected",
        "gates": gates,
        "selected_instance": selected,
        "p_world": p_world,
        "p_base": p_base,
        "target": target,
        "current_tcp": current_tcp,
        "safe_target": safe_target,
    }
