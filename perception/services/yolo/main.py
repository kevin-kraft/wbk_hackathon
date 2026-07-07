"""YOLO detection service — FastAPI app (uvicorn ... --port 8001)."""

from __future__ import annotations

from ..shared.app_factory import create_service_app
from ..shared.config import Settings
from ..shared.schemas import YoloResponse, YoloRequest
from .model import YoloModel

settings = Settings()
model = YoloModel(settings)
app = create_service_app(service_name="yolo", model=model)


@app.post("/infer", response_model=YoloResponse)
def infer(req: YoloRequest) -> YoloResponse:
    return model.infer(req)
