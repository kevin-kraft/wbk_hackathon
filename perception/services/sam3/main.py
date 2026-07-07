"""SAM3 segmentation service — FastAPI app (uvicorn ... --port 8002)."""

from __future__ import annotations

from fastapi import Depends

from ..shared.app_factory import create_service_app
from ..shared.auth import require_token
from ..shared.config import Settings
from ..shared.schemas import Sam3Request, Sam3Response
from .model import Sam3Backend

settings = Settings()
model = Sam3Backend(settings)
app = create_service_app(service_name="sam3", model=model)


@app.post("/infer", response_model=Sam3Response, dependencies=[Depends(require_token)])
def infer(req: Sam3Request) -> Sam3Response:
    return model.infer(req)
