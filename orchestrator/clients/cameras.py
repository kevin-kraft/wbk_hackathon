"""Concrete camera clients for the non-mock path.

- `OpenCVInspectionCamera` — the plain inspection webcam the arm presents parts to.
- `StaticSceneCamera` — serves a fixed RGB(-D) frame from files, a stand-in until
  a real RGB-D scene camera (e.g. RealSense) or a camera service is wired.
"""

from __future__ import annotations

import base64

from ..models import SceneFrame


class OpenCVInspectionCamera:
    def __init__(self, index: int = 0) -> None:
        self.index = index

    def capture(self) -> str:
        import cv2

        cap = cv2.VideoCapture(self.index)
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok:
            raise RuntimeError(f"inspection camera {self.index} read failed")
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("failed to encode inspection frame")
        return base64.b64encode(buf.tobytes()).decode()


class StaticSceneCamera:
    def __init__(self, rgb_path: str, depth_path: str | None = None, K: list[float] | None = None) -> None:
        self.rgb_path = rgb_path
        self.depth_path = depth_path
        self.K = K

    def _b64(self, path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def capture_scene(self) -> SceneFrame:
        return SceneFrame(
            rgb_b64=self._b64(self.rgb_path),
            depth_b64=self._b64(self.depth_path) if self.depth_path else None,
            K=self.K,
        )
