"""FastAPI smoke tests for the perception services.

Weights are never loaded — each service's module-level `model` is monkeypatched
so `model.load()` becomes a no-op and `model.infer()` returns a canned response.
This exercises the actual route wiring / response_model validation without
requiring ultralytics/transformers/torch.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.locateanything import main as locate_main
from services.shared.schemas import (
    Detection,
    BBox,
    LocateResponse,
    Location,
    Point,
    Sam3Response,
    YoloResponse,
)
from services.sam3 import main as sam3_main
from services.yolo import main as yolo_main


def test_yolo_health_and_infer(monkeypatch):
    monkeypatch.setattr(yolo_main.model, "load", lambda: setattr(yolo_main.model, "_loaded", True))
    canned = YoloResponse(
        detections=[Detection(box=BBox(x1=0, y1=0, x2=1, y2=1), score=0.9, class_id=0, label="bolt")],
        width=10,
        height=10,
        model="yolo11n.pt",
        inference_ms=1.0,
    )
    monkeypatch.setattr(yolo_main.model, "infer", lambda req: canned)

    with TestClient(yolo_main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["loaded"] is True
        assert health.json()["service"] == "yolo"

        resp = client.post("/infer", json={"image_b64": "abc"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["width"] == 10
        assert body["detections"][0]["label"] == "bolt"


def test_sam3_infer_returns_masks(monkeypatch):
    monkeypatch.setattr(sam3_main.model, "load", lambda: setattr(sam3_main.model, "_loaded", True))
    canned = Sam3Response(masks=[], width=5, height=5, model="facebook/sam3", inference_ms=0.5)
    monkeypatch.setattr(sam3_main.model, "infer", lambda req: canned)

    with TestClient(sam3_main.app) as client:
        resp = client.post("/infer", json={"image_b64": "abc", "text": "a bolt"})
        assert resp.status_code == 200
        assert resp.json()["masks"] == []


def test_locateanything_infer_returns_locations(monkeypatch):
    monkeypatch.setattr(
        locate_main.model, "load", lambda: setattr(locate_main.model, "_loaded", True)
    )
    canned = LocateResponse(
        locations=[Location(point=Point(x=1, y=1), score=1.0, label="bolt")],
        width=10,
        height=10,
        model="nvidia/LocateAnything-3B",
        inference_ms=2.0,
    )
    monkeypatch.setattr(locate_main.model, "infer", lambda req: canned)

    with TestClient(locate_main.app) as client:
        resp = client.post("/infer", json={"image_b64": "abc", "query": "the bolt"})
        assert resp.status_code == 200
        assert resp.json()["locations"][0]["label"] == "bolt"


def test_root_info_route_lists_endpoints():
    # `/` never touches model.load()/loaded, so it's safe to hit without
    # entering the TestClient as a context manager (which would otherwise run
    # the lifespan and call the real, heavy-dependency model.load()).
    client = TestClient(yolo_main.app)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "yolo"
    assert "/infer" in body["endpoints"]
