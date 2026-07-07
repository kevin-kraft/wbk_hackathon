from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import env
from app.services import calibration
from app.services import hover_service
from app.services import robot_control


router = APIRouter(prefix="/robot", tags=["robot-workflows"])


class RawRobotCommand(BaseModel):
    function_name: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class CalibrationPointRequest(BaseModel):
    p_world: list[float] = Field(min_length=3, max_length=3)
    q_base: list[float] | None = Field(default=None, min_length=3, max_length=3)
    table_origin: list[float] | None = Field(default=None, min_length=3, max_length=3)
    meta: dict[str, Any] = Field(default_factory=dict)


class CalibrationSolveRequest(BaseModel):
    tool_down_rpy: list[float] | None = Field(default=None, min_length=3, max_length=3)
    tool_down_from_tcp: bool = False


class HoverPlanRequest(BaseModel):
    pose_result: dict[str, Any] | None = None
    image_path: str | None = None
    part: str | None = None
    instance_id: int | None = None
    min_conf: float | None = None
    hover_clearance: float | None = None
    hover_z_abs: float | None = None


class HoverExecuteRequest(HoverPlanRequest):
    confirmation: str
    speed: float | None = None


@router.get("/probe")
async def probe_robot():
    return await robot_control.probe()


@router.post("/raw")
async def execute_raw_robot_command(command: RawRobotCommand):
    if not env.ALLOW_RAW_ROBOT_COMMANDS:
        raise HTTPException(status_code=403, detail="raw robot commands are disabled")
    return await robot_control.call_robot(command.function_name, command.args, command.kwargs)


@router.get("/calibration")
async def get_calibration():
    try:
        return calibration.load_calibration()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="no calibration file found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/calibration/points")
async def add_calibration_point(request: CalibrationPointRequest):
    try:
        session = calibration.load_session()
    except FileNotFoundError:
        session = {"points": []}

    if request.table_origin is not None:
        session["table_origin"] = request.table_origin

    q_base = request.q_base
    if q_base is None:
        q_base = (await robot_control.get_tcp_pose())[:3]

    session = calibration.add_correspondence(
        session,
        request.p_world,
        q_base,
        meta=request.meta,
    )
    calibration.save_session(session)
    return {"status": "ok", "n_points": len(session["points"]), "session": session}


@router.post("/calibration/solve")
async def solve_calibration(request: CalibrationSolveRequest):
    try:
        session = calibration.load_session()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="no calibration session found")

    tool_down_rpy = request.tool_down_rpy
    if request.tool_down_from_tcp:
        tool_down_rpy = (await robot_control.get_tcp_pose())[3:]

    try:
        result = calibration.solve_calibration(session, tool_down_rpy=tool_down_rpy)
        calibration.save_calibration(result)
        calibration.validate_calibration(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {"status": "ok", "calibration": result}


@router.post("/hover/plan")
async def plan_hover(request: HoverPlanRequest):
    try:
        return await hover_service.plan_hover(**request.dict())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="no calibration file found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/hover/execute")
async def execute_hover(request: HoverExecuteRequest):
    try:
        return await hover_service.execute_hover(**request.dict())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="no calibration file found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
