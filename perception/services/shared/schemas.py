"""Shared request/response contracts for the perception microservices.

These types are the *stable interface* the downstream grasp-planning and movement
modules will depend on. Keep them model-agnostic: a YOLO detection and a
LocateAnything hit both surface as boxes/points/scores, so the consumer does not
need to know which model produced them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Shared image input                                                          #
# --------------------------------------------------------------------------- #
class ImageInput(BaseModel):
    """Every /infer request carries the image as a base64 string.

    Base64-in-JSON keeps service-to-service calls trivial (no multipart). A
    `data:image/...;base64,` URI prefix is tolerated and stripped on decode.
    """

    image_b64: str = Field(..., description="Base64-encoded PNG/JPEG bytes (data-URI prefix optional).")


# --------------------------------------------------------------------------- #
# Health / meta                                                               #
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    status: str  # "ok" | "loading"
    service: str
    model: str
    device: str
    loaded: bool


# --------------------------------------------------------------------------- #
# Geometry primitives (shared across all three models)                        #
# --------------------------------------------------------------------------- #
class BBox(BaseModel):
    """Axis-aligned box in pixel coordinates, top-left origin."""

    x1: float
    y1: float
    x2: float
    y2: float


class Point(BaseModel):
    """A pixel coordinate. `label` follows the SAM prompt convention:
    1 = foreground / positive, 0 = background / negative."""

    x: float
    y: float
    label: int = 1


# --------------------------------------------------------------------------- #
# YOLO — object detection                                                     #
# --------------------------------------------------------------------------- #
class YoloRequest(ImageInput):
    conf: float = 0.25
    iou: float = 0.45
    classes: list[int] | None = None  # restrict to these class ids
    max_det: int = 300


class Detection(BaseModel):
    box: BBox
    score: float
    class_id: int
    label: str


class YoloResponse(BaseModel):
    detections: list[Detection]
    width: int
    height: int
    model: str
    inference_ms: float


# --------------------------------------------------------------------------- #
# YOLO-Seg — instance segmentation (trained parts model)                      #
# Boxes AND per-instance masks in one pass, keyed to the same class vocabulary #
# as the detector. Unlike SAM3/LocateAnything it is closed-vocab (no prompt).  #
# --------------------------------------------------------------------------- #
class YoloSegRequest(ImageInput):
    conf: float = 0.25
    iou: float = 0.45
    classes: list[int] | None = None  # restrict to these class ids
    max_det: int = 300


class SegInstance(BaseModel):
    box: BBox
    mask_b64_png: str  # single-channel (L) PNG, full-res, base64-encoded
    score: float
    class_id: int
    label: str


class YoloSegResponse(BaseModel):
    instances: list[SegInstance]
    width: int
    height: int
    model: str
    inference_ms: float


# --------------------------------------------------------------------------- #
# SAM3 — promptable segmentation                                              #
# --------------------------------------------------------------------------- #
class Sam3Request(ImageInput):
    """Prompt the segmenter with any combination of points, boxes, or text.
    (Text/concept prompting is a SAM3 feature; ignored if the loaded backend
    does not support it.)"""

    points: list[Point] | None = None
    boxes: list[BBox] | None = None
    text: str | None = None
    multimask_output: bool = False


class MaskResult(BaseModel):
    mask_b64_png: str  # single-channel (L) PNG, base64-encoded
    score: float
    box: BBox | None = None
    label: str | None = None


class Sam3Response(BaseModel):
    masks: list[MaskResult]
    width: int
    height: int
    model: str
    inference_ms: float


# --------------------------------------------------------------------------- #
# LocateAnything — text-prompted localization / pointing                      #
# --------------------------------------------------------------------------- #
class LocateRequest(ImageInput):
    query: str  # natural-language description of what to locate
    top_k: int = 10
    conf: float = 0.2


class Location(BaseModel):
    point: Point
    box: BBox | None = None
    score: float
    label: str


class LocateResponse(BaseModel):
    locations: list[Location]
    width: int
    height: int
    model: str
    inference_ms: float
