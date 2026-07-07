"""Force the mock backend before scene_camera.app is imported (no Zivid/camera)."""

import os

os.environ.setdefault("SCENE_CAMERA_BACKEND", "mock")
