"""Shared-token auth on a pose service (/pose). Runner is monkeypatched so no GPU
stack is needed. Representative of foundationpose/gigapose (same shared
dependency). /health stays open.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi.testclient import TestClient

from foundationpose_svc import app as fp_app_module

TOKEN = "s3cret-token"
_K = [100.0, 0.0, 32.0, 0.0, 100.0, 24.0, 0.0, 0.0, 1.0]
_IDENTITY = np.asarray([[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]])


def _png_b64(arr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def _body() -> dict:
    return {
        "rgb_b64": _png_b64(np.zeros((4, 4, 3), dtype=np.uint8)),
        "depth_b64": _png_b64(np.full((4, 4), 1000, dtype=np.uint16)),
        "K": _K,
        "instances": [{"id": 0, "class": "housing", "mask_b64": _png_b64(np.full((4, 4), 255, dtype=np.uint8))}],
    }


def _prep(monkeypatch):
    monkeypatch.setattr(fp_app_module.runner, "load", lambda: setattr(fp_app_module.runner, "_loaded", True))
    monkeypatch.setattr(
        fp_app_module.runner, "estimate", lambda cls, K, rgb, depth, mask, iterations=None: _IDENTITY
    )


def test_health_open(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _prep(monkeypatch)
    with TestClient(fp_app_module.app) as client:
        assert client.get("/health").status_code == 200


def test_pose_rejects_without_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _prep(monkeypatch)
    with TestClient(fp_app_module.app) as client:
        assert client.post("/pose", json=_body()).status_code == 401


def test_pose_accepts_bearer(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _prep(monkeypatch)
    with TestClient(fp_app_module.app) as client:
        r = client.post("/pose", json=_body(), headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200


def test_pose_open_when_unset(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    _prep(monkeypatch)
    with TestClient(fp_app_module.app) as client:
        assert client.post("/pose", json=_body()).status_code == 200
