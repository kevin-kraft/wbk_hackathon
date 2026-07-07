import json
import socket
from typing import Any

import app.env as env

class RobotSocketClient:
    def __init__(self, host: str, port: int, timeout: float):
        self.host = host
        self.port = port
        self.timeout = timeout

    def call(
        self,
        function_name: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        args = args or []
        kwargs = kwargs or {}

        payload = {
            "function": function_name,
            "args": args,
            "kwargs": kwargs,
        }

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect((self.host, self.port))
                s.sendall(json.dumps(payload).encode("utf-8"))

                response = s.recv(8192)
                if not response:
                    return {
                        "result": None,
                        "error": "Robot socket returned empty response",
                    }

                return json.loads(response.decode("utf-8"))

        except Exception as e:
            return {
                "result": None,
                "error": str(e),
            }


robot_socket_client = RobotSocketClient(
    host=env.ROBOT_HOST,
    port=env.ROBOT_PORT,
    timeout=env.SOCKET_TIMEOUT,
)