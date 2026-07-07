import socket
import json
import asyncio
import uvicorn

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

class RobotCommand(BaseModel):
    function_name: str
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}

app = FastAPI()

executor = ThreadPoolExecutor(max_workers=10)

def _raw_socket_request(function_name, args=None, kwargs=None):
    args = args or []
    kwargs = kwargs or {}
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(('192.168.2.13', 65432))
            
            payload = {"function": function_name, "args": args, "kwargs": kwargs}
            s.sendall(json.dumps(payload).encode('utf-8'))
            
            response = s.recv(8192)
            return json.loads(response.decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}
    
@app.post('/command')
async def execute_remote_command(cmd: RobotCommand):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _raw_socket_request, cmd.function_name, cmd.args, cmd.kwargs)

def robot_joint_states(function_name, *args, **kwargs):
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('192.168.2.13', 65432))
        payload = {"function": function_name, "args": args, "kwargs": kwargs}
        s.sendall(json.dumps(payload).encode('utf-8'))
        response = s.recv(8192)
        return json.loads(response.decode('utf-8'))
    
@app.websocket('/ws/joint_states')
async def joint_stream(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({'msg': 'Jetson Bridge Activate'})
    
    loop = asyncio.get_event_loop()
    try:
        while True:
            data = await loop.run_in_executor(executor, _raw_socket_request, 'get_current_joint_angles')
            
            await websocket.send_json(data)
            
            await asyncio.sleep(0.05)
            
    except Exception as e:
        print(f"WebSocket Error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    print('Starting LARA5 API Server on Port 8000')
    uvicorn.run(
        app,
        host='172.22.192.166',
        port=8000,
        log_level='info'
    )
