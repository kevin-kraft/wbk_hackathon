from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app import env
from app.robot_socket_client import robot_socket_client


executor = ThreadPoolExecutor(max_workers=4)
motion_lock = asyncio.Lock()


async def call_robot(function_name: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        robot_socket_client.call,
        function_name,
        args or [],
        kwargs or {},
    )


async def call_robot_result(function_name: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None) -> Any:
    response = await call_robot(function_name, args, kwargs)
    if isinstance(response, dict) and response.get("error"):
        raise RuntimeError(response["error"])
    if isinstance(response, dict) and "result" in response:
        return response["result"]
    return response


async def probe() -> dict[str, Any]:
    telemetry = {}
    for name in ("get_tcp_pose", "get_current_joint_angles", "get_errors", "motion_status", "program_status"):
        telemetry[name] = await call_robot(name, [], {})
    return telemetry


async def get_tcp_pose() -> list[float]:
    result = await call_robot_result("get_tcp_pose", [], {})
    return [float(v) for v in result]


async def move_linear(target: list[float], *, speed: float | None = None, acceleration: float | None = None) -> dict[str, Any]:
    speed = min(float(speed if speed is not None else env.SPEED_CAP_MS), env.SPEED_CAP_MS)
    acceleration = min(float(acceleration if acceleration is not None else env.ACCEL_CAP), env.ACCEL_CAP)
    current = await get_tcp_pose()
    current_joint_angles = await call_robot_result("get_current_joint_angles", [], {})
    await call_robot_result("init_program", [], {})
    return await call_robot(
        "move_linear",
        [],
        {
            "speed": speed,
            "acceleration": acceleration,
            "target_pose": [current, target],
            "current_joint_angles": current_joint_angles,
        },
    )
