"""6DoF pose stage client — talks to foundationpose/gigapose (/pose)."""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig
from ..models import PartDetection, Pose, SceneFrame


class HttpPose:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.c = config
        self._http = httpx.Client(timeout=config.http_timeout_s)

    def estimate(self, frame: SceneFrame, part: PartDetection) -> Pose:
        if not part.mask_b64:
            raise ValueError("pose estimation needs a segmentation mask on the part")
        payload = {
            "rgb_b64": frame.rgb_b64,
            "depth_b64": frame.depth_b64,
            "K": frame.K,
            "instances": [{"id": part.id, "class": part.class_name, "mask_b64": part.mask_b64}],
        }
        r = self._http.post(f"{self.c.pose_url}/pose", json=payload)
        r.raise_for_status()
        poses = r.json().get("poses", [])
        if not poses:
            raise RuntimeError(f"no pose returned for {part.class_name}")
        p = poses[0]
        return Pose(T_cam_obj=p["T_cam_obj"], score=p.get("score"), stage=p.get("stage"))
