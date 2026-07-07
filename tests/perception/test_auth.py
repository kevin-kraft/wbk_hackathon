"""Shared-token auth on a perception service (/infer). Model is monkeypatched so
no torch/weights are needed. Representative of yolo/sam3/locateanything (same
shared dependency). /health stays open.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.shared.schemas import YoloResponse
from services.yolo import main as yolo_main

TOKEN = "s3cret-token"


def _prep(monkeypatch):
    monkeypatch.setattr(yolo_main.model, "load", lambda: setattr(yolo_main.model, "_loaded", True))
    canned = YoloResponse(detections=[], width=1, height=1, model="yolo11n.pt", inference_ms=0.0)
    monkeypatch.setattr(yolo_main.model, "infer", lambda req: canned)


def test_health_open(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _prep(monkeypatch)
    with TestClient(yolo_main.app) as client:
        assert client.get("/health").status_code == 200


def test_infer_open_when_unset(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    _prep(monkeypatch)
    with TestClient(yolo_main.app) as client:
        assert client.post("/infer", json={"image_b64": "abc"}).status_code == 200


def test_infer_rejects_without_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _prep(monkeypatch)
    with TestClient(yolo_main.app) as client:
        assert client.post("/infer", json={"image_b64": "abc"}).status_code == 401


def test_infer_accepts_bearer(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    _prep(monkeypatch)
    with TestClient(yolo_main.app) as client:
        r = client.post("/infer", json={"image_b64": "abc"}, headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200
