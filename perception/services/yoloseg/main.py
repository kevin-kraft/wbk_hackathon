"""YOLO-Seg service — FastAPI app (uvicorn services.yoloseg.main:app --port 8007)."""

from __future__ import annotations

from fastapi import Depends

from ..shared.app_factory import create_service_app
from ..shared.auth import require_token
from ..shared.config import Settings
from ..shared.schemas import YoloSegRequest, YoloSegResponse
from .model import YoloSegModel

settings = Settings()
model = YoloSegModel(settings)
app = create_service_app(service_name="yoloseg", model=model)


@app.post("/infer", response_model=YoloSegResponse, dependencies=[Depends(require_token)])
def infer(req: YoloSegRequest) -> YoloSegResponse:
    return model.infer(req)
