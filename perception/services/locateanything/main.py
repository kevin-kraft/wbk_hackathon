"""LocateAnything localization service — FastAPI app (uvicorn ... --port 8003)."""

from __future__ import annotations

from ..shared.app_factory import create_service_app
from ..shared.config import Settings
from ..shared.schemas import LocateRequest, LocateResponse
from .model import LocateAnythingBackend

settings = Settings()
model = LocateAnythingBackend(settings)
app = create_service_app(service_name="locateanything", model=model)


@app.post("/infer", response_model=LocateResponse)
def infer(req: LocateRequest) -> LocateResponse:
    return model.infer(req)
