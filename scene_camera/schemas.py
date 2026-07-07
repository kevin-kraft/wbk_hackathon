"""Wire schemas. `SceneCaptureResponse` is a superset of the orchestrator's
`SceneFrame` (rgb_b64 / depth_b64 / K) plus capture metadata."""

from __future__ import annotations

from pydantic import BaseModel


class SceneHealth(BaseModel):
    status: str
    service: str = "scene_camera"
    backend: str
    ready: bool


class SceneCaptureResponse(BaseModel):
    rgb_b64: str
    depth_b64: str | None = None  # uint16-mm PNG, matches SceneFrame
    K: list[float] | None = None  # flat-9 row-major intrinsics
    width: int
    height: int
    backend: str
    capture_ms: float
