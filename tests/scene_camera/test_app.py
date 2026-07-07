"""Service wiring: health open, /capture gated + returns a valid SceneFrame."""

import base64

import cv2
import numpy as np
from fastapi.testclient import TestClient

from scene_camera.app import app

client = TestClient(app)


def _bytes(b64: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), np.uint8)


def test_health_open_and_reports_backend():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["backend"] == "mock"
    assert body["service"] == "scene_camera"


def test_capture_returns_sceneframe_shape():
    r = client.post("/capture")
    assert r.status_code == 200
    d = r.json()
    assert set(d) >= {"rgb_b64", "depth_b64", "K", "width", "height", "backend"}
    assert d["backend"] == "mock"
    # decode like the pose stage does
    rgb = cv2.cvtColor(cv2.imdecode(_bytes(d["rgb_b64"]), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    assert rgb.shape == (d["height"], d["width"], 3)
    depth_m = cv2.imdecode(_bytes(d["depth_b64"]), cv2.IMREAD_UNCHANGED).astype(np.float32) / 1000.0
    assert depth_m.shape == (d["height"], d["width"])
    assert 0.4 < depth_m.max() <= 1.0  # mock plane ~0.5..1.0 m
    assert len(d["K"]) == 9


def test_capture_requires_token_when_set(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", "disassemblr")
    assert client.get("/health").status_code == 200  # still open
    assert client.post("/capture").status_code == 401
    assert client.post("/capture", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.post("/capture", headers={"Authorization": "Bearer disassemblr"})
    assert ok.status_code == 200
    # query-param form (for parity with the browser SSE/WS case)
    assert client.post("/capture?token=disassemblr").status_code == 200
