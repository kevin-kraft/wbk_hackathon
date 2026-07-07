"""FastAPI smoke tests for the two pose services.

The module-level `runner` (`FoundationPoseRunner()` / `GigaPoseRunner()`) is
cheap to construct — heavy imports (`nvdiffrast`, `trimesh`, `gigapose_infer`)
only happen inside `.load()`. We monkeypatch `.load()` to a no-op and
`.estimate()` to return a canned pose so the route wiring / response_model
validation is exercised without any GPU stack.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi.testclient import TestClient

from foundationpose_svc import app as fp_app_module
from gigapose_svc import app as gp_app_module

_IDENTITY = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
_K = [100.0, 0.0, 32.0, 0.0, 100.0, 24.0, 0.0, 0.0, 1.0]


def _png_b64(arr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def _rgb_b64() -> str:
    return _png_b64(np.zeros((4, 4, 3), dtype=np.uint8))


def _depth_b64() -> str:
    return _png_b64(np.full((4, 4), 1000, dtype=np.uint16))


def _mask_b64() -> str:
    return _png_b64(np.full((4, 4), 255, dtype=np.uint8))


def test_foundationpose_health(monkeypatch):
    monkeypatch.setattr(fp_app_module.runner, "load", lambda: setattr(fp_app_module.runner, "_loaded", True))

    with TestClient(fp_app_module.app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "foundationpose"
        assert body["loaded"] is True


def test_foundationpose_pose_requires_depth(monkeypatch):
    monkeypatch.setattr(fp_app_module.runner, "load", lambda: setattr(fp_app_module.runner, "_loaded", True))

    with TestClient(fp_app_module.app) as client:
        resp = client.post(
            "/pose",
            json={
                "rgb_b64": _rgb_b64(),
                "K": _K,
                "instances": [{"id": 0, "class": "housing", "mask_b64": _mask_b64()}],
            },
        )
        assert resp.status_code == 400


def test_foundationpose_pose_happy_path(monkeypatch):
    monkeypatch.setattr(fp_app_module.runner, "load", lambda: setattr(fp_app_module.runner, "_loaded", True))
    monkeypatch.setattr(
        fp_app_module.runner, "estimate", lambda cls, K, rgb, depth, mask, iterations=None: np.asarray(_IDENTITY)
    )

    with TestClient(fp_app_module.app) as client:
        resp = client.post(
            "/pose",
            json={
                "rgb_b64": _rgb_b64(),
                "depth_b64": _depth_b64(),
                "K": _K,
                "instances": [{"id": 0, "class": "housing", "mask_b64": _mask_b64()}],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["poses"][0]["class"] == "housing"
        assert body["poses"][0]["T_cam_obj"] == _IDENTITY
        assert body["timings"]["num_posed"] == 1


def test_gigapose_pose_rgb_only_pipeline_does_not_require_depth(monkeypatch):
    monkeypatch.setattr(gp_app_module.runner, "load", lambda: setattr(gp_app_module.runner, "_loaded", True))
    monkeypatch.setattr(
        gp_app_module.runner,
        "estimate",
        lambda cls, K, rgb, mask, depth, iterations, hypotheses, kabsch: (
            np.asarray(_IDENTITY),
            0.9,
            "refined",
        ),
    )

    with TestClient(gp_app_module.app) as client:
        resp = client.post(
            "/pose",
            json={
                "rgb_b64": _rgb_b64(),
                "K": _K,
                "instances": [{"id": 1, "class": "bracket", "mask_b64": _mask_b64()}],
                "pipeline": "rgb",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["poses"][0]["class"] == "bracket"
        assert body["poses"][0]["score"] == 0.9
        assert body["poses"][0]["stage"] == "refined"


def test_gigapose_pose_rgbd_pipeline_requires_depth(monkeypatch):
    monkeypatch.setattr(gp_app_module.runner, "load", lambda: setattr(gp_app_module.runner, "_loaded", True))

    with TestClient(gp_app_module.app) as client:
        resp = client.post(
            "/pose",
            json={
                "rgb_b64": _rgb_b64(),
                "K": _K,
                "instances": [{"id": 1, "class": "bracket", "mask_b64": _mask_b64()}],
                "pipeline": "rgbd",
            },
        )
        assert resp.status_code == 400
