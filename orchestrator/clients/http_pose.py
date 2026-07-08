"""6DoF pose stage client — talks to foundationpose/gigapose (/pose)."""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig
from ..models import PartDetection, Pose, SceneFrame


class HttpPose:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.c = config
        self._http = httpx.Client(timeout=config.http_timeout_s, headers=config.auth_headers)

    def estimate(self, frame: SceneFrame, part: PartDetection) -> Pose:
        if not part.mask_b64:
            raise ValueError("pose estimation needs a segmentation mask on the part")
        pipeline = (self.c.pose_pipeline or "rgbd").lower()
        payload = {
            "rgb_b64": frame.rgb_b64,
            "depth_b64": frame.depth_b64,
            "K": frame.K,
            "pipeline": pipeline,
            "instances": [{"id": part.id, "class": part.class_name, "mask_b64": part.mask_b64}],
        }
        if pipeline == "2d" and self.c.pose_plane_z is not None:
            payload["plane_z"] = self.c.pose_plane_z
        # '2d'/'rgb' are GigaPose-only pipelines; 'rgbd' stays on the default
        # pose service (FoundationPose). gigapose_url falls back to pose_url.
        url = self.c.gigapose_url if pipeline in ("2d", "rgb") else self.c.pose_url
        url = url or self.c.pose_url
        r = self._http.post(f"{url}/pose", json=payload)
        r.raise_for_status()
        poses = r.json().get("poses", [])
        if not poses:
            raise RuntimeError(f"no pose returned for {part.class_name}")
        p = poses[0]
        return Pose(T_cam_obj=p["T_cam_obj"], score=p.get("score"), stage=p.get("stage"))
