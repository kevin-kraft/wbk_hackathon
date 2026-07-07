"""Capture backends for the scene camera.

Each backend returns a `RawCapture` (RGB uint8, depth in mm, flat-9 intrinsics);
the service layer encodes that into the SceneFrame wire format. The Zivid SDK and
a physical camera are needed only by `ZividBackend` — `mock`/`file` let the
service run and be tested anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Settings


@dataclass
class RawCapture:
    rgb: np.ndarray  # HxWx3 uint8, RGB order
    depth_mm: np.ndarray | None  # HxW float32, millimetres (NaN allowed)
    K: list[float] | None  # flat-9 row-major intrinsics


class Backend:
    name = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def capture(self) -> RawCapture:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def ready(self) -> bool:
        return True


class MockBackend(Backend):
    """Synthetic frame — no hardware. For dev/CI and dashboard smoke tests."""

    name = "mock"

    def capture(self) -> RawCapture:
        h, w = 480, 640
        yy, xx = np.mgrid[0:h, 0:w]
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        rgb[..., 0] = (xx * 255 // w).astype(np.uint8)
        rgb[..., 1] = (yy * 255 // h).astype(np.uint8)
        rgb[..., 2] = 128
        # A slanted plane ~0.5-1.0 m away, in mm.
        depth_mm = (500.0 + xx / w * 500.0).astype(np.float32)
        K = self.settings.k_override or [600.0, 0.0, w / 2, 0.0, 600.0, h / 2, 0.0, 0.0, 1.0]
        return RawCapture(rgb=rgb, depth_mm=depth_mm, K=K)


class FileBackend(Backend):
    """Read a fixed RGB(-D) capture from disk (mirrors the orchestrator stand-in)."""

    name = "file"

    def capture(self) -> RawCapture:
        import cv2

        if not self.settings.rgb_path:
            raise RuntimeError("file backend needs SCENE_RGB_PATH")
        bgr = cv2.imread(self.settings.rgb_path, cv2.IMREAD_COLOR)
        if bgr is None:
            raise RuntimeError(f"could not read {self.settings.rgb_path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        depth_mm = None
        if self.settings.depth_path:
            raw = cv2.imread(self.settings.depth_path, cv2.IMREAD_UNCHANGED)
            if raw is None:
                raise RuntimeError(f"could not read {self.settings.depth_path}")
            depth_mm = raw.astype(np.float32)  # assumed already in mm
        return RawCapture(rgb=rgb, depth_mm=depth_mm, K=self.settings.k_override)


class ZividBackend(Backend):
    """Real Zivid capture (Jetson, camera on USB3/GigE). Needs the `zivid` SDK."""

    name = "zivid"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._app = None
        self._camera = None
        self._settings_obj = None

    def _connect(self) -> None:
        import zivid  # lazy: only needed on the Jetson with the SDK installed

        if self._app is None:
            self._app = zivid.Application()
        if self._camera is None:
            self._camera = self._app.connect_camera()
        if self._settings_obj is None:
            if self.settings.zivid_settings_path:
                self._settings_obj = zivid.Settings.load(self.settings.zivid_settings_path)
            else:
                self._settings_obj = zivid.Settings(
                    acquisitions=[zivid.Settings.Acquisition()]
                )

    @property
    def ready(self) -> bool:
        try:
            self._connect()
            return self._camera is not None
        except Exception:
            return False

    def _intrinsics(self) -> list[float] | None:
        if self.settings.k_override:
            return self.settings.k_override
        try:
            import zivid.experimental.calibration as zcal

            cm = zcal.intrinsics(self._camera).camera_matrix
            return [cm.fx, 0.0, cm.cx, 0.0, cm.fy, cm.cy, 0.0, 0.0, 1.0]
        except Exception:
            return None  # let the orchestrator fall back to SCENE_K if needed

    def capture(self) -> RawCapture:
        self._connect()
        frame = self._camera.capture(self._settings_obj)
        try:
            pc = frame.point_cloud()
            xyz = pc.copy_data("xyz")  # HxWx3 float32 mm, NaN for no-return
            rgba = pc.copy_data("rgba")  # HxWx4 uint8
            rgb = np.ascontiguousarray(rgba[:, :, :3])
            depth_mm = np.ascontiguousarray(xyz[:, :, 2]).astype(np.float32)
            return RawCapture(rgb=rgb, depth_mm=depth_mm, K=self._intrinsics())
        finally:
            frame.release()


def make_backend(settings: Settings) -> Backend:
    name = (settings.backend or "zivid").lower()
    if name == "mock":
        return MockBackend(settings)
    if name == "file":
        return FileBackend(settings)
    if name == "zivid":
        return ZividBackend(settings)
    raise ValueError(f"unknown SCENE_CAMERA_BACKEND: {settings.backend!r}")
