import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.robot_socket_client import robot_socket_client


router = APIRouter(tags=["robot-commands"])

executor = ThreadPoolExecutor(max_workers=4)


class RobotCommandRequest(BaseModel):
    command: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class RobotCommandResponse(BaseModel):
    command: str
    status: str
    result: Any | None = None
    error: str | None = None


READ_COMMANDS = {
    "get_current_joint_angles",
    "get_current_joint_angles_with_timestamp",
    "get_current_joint_velocities",
    "get_current_joint_torques",
    "get_tcp_pose",
    "get_tcp_pose_quaternion",
    "get_flange_pose",
    "motion_status",
    "program_status",
    "get_errors",
    "get_diagnostics",
}


MOTION_COMMANDS = {
    "move_joint",
    "move_joint_relative",
    "move_linear",
    "move_linear_relative",
    "move_circular",
    "move_composite",
    "gripper",
    "grasp",
    "release",
    "pause",
    "stop",
    "unpause",
}


ALLOWED_COMMANDS = READ_COMMANDS | MOTION_COMMANDS


async def call_robot(function_name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        executor,
        robot_socket_client.call,
        function_name,
        args,
        kwargs,
    )


@router.post("/robot/execute/", response_model=RobotCommandResponse)
async def execute_robot_command(request: RobotCommandRequest):
    if request.command not in ALLOWED_COMMANDS:
        raise HTTPException(
            status_code=403,
            detail=f"Command not allowed: {request.command}",
        )

    try:
        if request.command in READ_COMMANDS:
            result = await call_robot(
                request.command,
                request.args,
                request.kwargs,
            )

            return RobotCommandResponse(
                command=request.command,
                status="ok",
                result=result,
            )

        # Motion command lifecycle:
        # init_program -> actual command -> stop
        await call_robot("init_program", [], {})

        # try:
        result = await call_robot(
            request.command,
            request.args,
            request.kwargs,
        )

        if isinstance(result, dict) and result.get("error"):
            return RobotCommandResponse(
                command=request.command,
                status="error",
                result=result.get("result"),
                error=result.get("error"),
            )

        return RobotCommandResponse(
            command=request.command,
            status="ok",
            result=result,
        )

        # finally:
        #     # Always try to stop after motion command.
        #     # This must run even if the command fails.
        #     try:
        #         await call_robot("stop", [], {})
        #     except Exception as stop_error:
        #         print(f"Robot stop failed after command {request.command}: {stop_error}", flush=True)

    except HTTPException:
        raise

    except Exception as e:
        return RobotCommandResponse(
            command=request.command,
            status="error",
            error=str(e),
        )