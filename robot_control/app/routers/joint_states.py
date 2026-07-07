import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import app.env as env
from app.robot_socket_client import robot_socket_client


router = APIRouter(tags=["joint-states"])

executor = ThreadPoolExecutor(max_workers=4)


@router.websocket("/ws/joint_states")
async def joint_stream(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"msg": "Jetson Bridge Active"})

    loop = asyncio.get_running_loop()

    try:
        while True:
            data = await loop.run_in_executor(
                executor,
                robot_socket_client.call,
                "get_current_joint_angles",
                [],
                {},
            )
            print(f"Data style: {data}")
            await websocket.send_json(data)
            await asyncio.sleep(env.JOINT_STREAM_DT)

    except WebSocketDisconnect:
        print("WebSocket disconnected", flush=True)

    except Exception as e:
        print(f"WebSocket error: {e}", flush=True)

    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass