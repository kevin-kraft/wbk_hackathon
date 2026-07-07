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
    # "zivid" (real camera), "mock" (synthetic frame), or "file" (read from disk).
    # Defaults to zivid — on the Jetson where the camera lives. Override to "mock"
    # for dev/CI on a machine without the SDK or camera.
    backend: str = field(default_factory=lambda: os.getenv("SCENE_CAMERA_BACKEND", "zivid"))

    # Optional Zivid Studio settings preset (YAML). Without it a default
    # single-acquisition capture is used — fine to smoke-test, tune per scene later.
    zivid_settings_path: str = field(default_factory=lambda: os.getenv("ZIVID_SETTINGS_PATH", ""))

    # Pin intrinsics instead of reading them from the SDK (flat-9 row-major JSON).
    k_override: list[float] | None = field(default_factory=_k_from_env)

    # Clamp for the 16-bit depth PNG (mm). Anything beyond becomes max.
    depth_max_mm: int = field(default_factory=lambda: int(os.getenv("SCENE_DEPTH_MAX_MM", "65535")))

    # file backend inputs (dev only).
    rgb_path: str = field(default_factory=lambda: os.getenv("SCENE_RGB_PATH", ""))
    depth_path: str = field(default_factory=lambda: os.getenv("SCENE_DEPTH_PATH", ""))
