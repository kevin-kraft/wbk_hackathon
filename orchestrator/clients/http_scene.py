"""Scene-camera client — talks to the Zivid capture service (POST /capture).

Satisfies the `SceneCamera` protocol, so it drops into the orchestrator in place
of `StaticSceneCamera` when `SCENE_CAMERA_URL` is set.
"""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig
from ..models import SceneFrame


class HttpSceneCamera:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.c = config
        self._http = httpx.Client(timeout=config.http_timeout_s, headers=config.auth_headers)

    def capture_scene(self) -> SceneFrame:
        r = self._http.post(f"{self.c.scene_camera_url}/capture", json={})
        r.raise_for_status()
        d = r.json()
        return SceneFrame(rgb_b64=d["rgb_b64"], depth_b64=d.get("depth_b64"), K=d.get("K"))
