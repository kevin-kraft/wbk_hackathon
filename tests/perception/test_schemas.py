"""services/shared/schemas.py — request defaults & validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.shared.schemas import (
    BBox,
    LocateRequest,
    Point,
    Sam3Request,
    YoloRequest,
)


def test_yolo_request_defaults():
    req = YoloRequest(image_b64="abc")

    assert req.conf == 0.25
    assert req.iou == 0.45
    assert req.classes is None
    assert req.max_det == 300


def test_yolo_request_requires_image_b64():
    with pytest.raises(ValidationError):
        YoloRequest()  # type: ignore[call-arg]


def test_yolo_request_accepts_class_restriction():
    req = YoloRequest(image_b64="abc", classes=[0, 3])
    assert req.classes == [0, 3]


def test_point_default_label_is_positive():
    p = Point(x=1.0, y=2.0)
    assert p.label == 1


def test_sam3_request_defaults_and_optional_prompts():
    req = Sam3Request(image_b64="abc")

    assert req.points is None
    assert req.boxes is None
    assert req.text is None
    assert req.multimask_output is False


def test_sam3_request_accepts_points_and_boxes():
    req = Sam3Request(
        image_b64="abc",
        points=[Point(x=1, y=2, label=0)],
        boxes=[BBox(x1=0, y1=0, x2=10, y2=10)],
    )
    assert req.points[0].label == 0
    assert req.boxes[0].x2 == 10


def test_locate_request_defaults():
    req = LocateRequest(image_b64="abc", query="the red bolt")

    assert req.top_k == 10
    assert req.conf == 0.2
    assert req.query == "the red bolt"


def test_locate_request_requires_query():
    with pytest.raises(ValidationError):
        LocateRequest(image_b64="abc")  # type: ignore[call-arg]
