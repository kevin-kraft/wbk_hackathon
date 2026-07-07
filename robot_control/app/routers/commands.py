import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter

from app.schemas import RobotCommand
from app.robot_socket_client import robot_socket_client


router = APIRouter(tags=["commands"])

executor = ThreadPoolExecutor(max_workers=10)


@router.post("/command")
async def execute_remote_command(cmd: RobotCommand):
    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        executor,
        robot_socket_client.call,
        cmd.function_name,
        cmd.args,
        cmd.kwargs,
    )