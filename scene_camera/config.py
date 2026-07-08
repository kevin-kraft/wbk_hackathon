"""Environment-driven configuration for the scene-camera capture service."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _k_from_env() -> list[float] | None:
    raw = os.getenv("SCENE_K")
    if not raw:
        return None
    k = json.loads(raw)
    if len(k) != 9:
        raise ValueError("SCENE_K must be a flat-9 row-major intrinsics list")
    return [float(v) for v in k]


@dataclass
class Settings:
    # "zivid" (real RGB-D camera), "rgbcam" (a plain 2D camera via OpenCV — the
    # new depth-less setup for slot localization), "mock" (synthetic frame), or
    # "file" (read from disk). Defaults to zivid. Override to "rgbcam" for the new
    # arm+camera, or "mock" for dev/CI without any camera.
    backend: str = field(default_factory=lambda: os.getenv("SCENE_CAMERA_BACKEND", "zivid"))

    # rgbcam backend: OpenCV VideoCapture index (or a device path / stream URL).
    cam_index: str = field(default_factory=lambda: os.getenv("SCENE_CAMERA_INDEX", "0"))

    # Optional Zivid Studio settings preset (YAML). Without it a default
    # single-acquisition capture is used — fine to smoke-test, tune per scene later.
    zivid_settings_path: str = field(default_factory=lambda: os.getenv("ZIVID_SETTINGS_PATH", ""))

    # Pin intrinsics instead of reading them from the SDK (flat-9 row-major JSON).
    k_override: list[float] | None = field(default_factory=_k_from_env)

    # Clamp for the 16-bit depth PNG (mm). Anything beyond becomes max.
    depth_max_mm: int = field(default_factory=lambda: int(os.getenv("SCENE_DEPTH_MAX_MM", "65535")))

    # Gray-world white balance on the Zivid RGB to neutralise its green colour
    # cast before encoding. "grayworld" (default) | "off".
    white_balance: str = field(default_factory=lambda: os.getenv("SCENE_WHITE_BALANCE", "grayworld"))

    # file backend inputs (dev only).
    rgb_path: str = field(default_factory=lambda: os.getenv("SCENE_RGB_PATH", ""))
    depth_path: str = field(default_factory=lambda: os.getenv("SCENE_DEPTH_PATH", ""))
