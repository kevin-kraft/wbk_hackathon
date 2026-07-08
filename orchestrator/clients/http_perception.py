"""Perception stage client — talks to the yolo/sam3/locateanything services."""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig
from ..models import Box, PartDetection, SceneFrame


class HttpPerception:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.c = config
        self._http = httpx.Client(timeout=config.http_timeout_s, headers=config.auth_headers)

    def next_part(self, frame: SceneFrame) -> PartDetection | None:
        # LocateAnything: text query -> ranked boxes/points.
        r = self._http.post(
            f"{self.c.perception_locate_url}/infer",
            json={"image_b64": frame.rgb_b64, "query": self.c.next_part_query, "top_k": 1},
        )
        r.raise_for_status()
        locations = r.json().get("locations", [])
        if not locations:
            return None
        loc = locations[0]
        b = loc.get("box")
        box = Box(x1=b["x1"], y1=b["y1"], x2=b["x2"], y2=b["y2"]) if b else None
        point = (loc["point"]["x"], loc["point"]["y"]) if loc.get("point") else None
        return PartDetection(
            class_name=loc.get("label") or self.c.next_part_query,
            score=loc.get("score", 1.0),
            box=box,
            point=point,
        )

    def locate(self, frame: SceneFrame, class_name: str) -> PartDetection | None:
        # Plan-driven grounding: same LocateAnything call as next_part, but the
        # query is the plan step's specific part, not the generic next-part prompt.
        r = self._http.post(
            f"{self.c.perception_locate_url}/infer",
            json={"image_b64": frame.rgb_b64, "query": class_name, "top_k": 1},
        )
        r.raise_for_status()
        locations = r.json().get("locations", [])
        if not locations:
            return None
        loc = locations[0]
        b = loc.get("box")
        box = Box(x1=b["x1"], y1=b["y1"], x2=b["x2"], y2=b["y2"]) if b else None
        point = (loc["point"]["x"], loc["point"]["y"]) if loc.get("point") else None
        return PartDetection(class_name=class_name, score=loc.get("score", 1.0), box=box, point=point)

    def segment(self, frame: SceneFrame, part: PartDetection) -> str | None:
        # SAM3: prefer box/point prompt, fall back to the class name as text.
        payload: dict = {"image_b64": frame.rgb_b64}
        if part.box:
            payload["boxes"] = [{"x1": part.box.x1, "y1": part.box.y1, "x2": part.box.x2, "y2": part.box.y2}]
        elif part.point:
            payload["points"] = [{"x": part.point[0], "y": part.point[1], "label": 1}]
        else:
            payload["text"] = part.class_name
        r = self._http.post(f"{self.c.perception_sam3_url}/infer", json=payload)
        r.raise_for_status()
        masks = r.json().get("masks", [])
        return masks[0]["mask_b64_png"] if masks else None

    def is_present(self, frame: SceneFrame, part: PartDetection) -> bool:
        # Present if SAM3 still finds the class by text prompt.
        r = self._http.post(
            f"{self.c.perception_sam3_url}/infer",
            json={"image_b64": frame.rgb_b64, "text": part.class_name},
        )
        r.raise_for_status()
        return len(r.json().get("masks", [])) > 0
