"""DDS cloud-detector proxy service — FastAPI app (uvicorn ... --port 8008).

Fronts the DeepDataSpace / IDEA cloud detectors (T-Rex2, DINO-X, Grounding-DINO,
DINO-XSeek) so they can be compared against the local perception stack through
the same request/response contract. See ``model.py`` for the model matrix.
"""

from __future__ import annotations

from fastapi import Depends

from ..shared.app_factory import create_service_app
from ..shared.auth import require_token
from ..shared.config import Settings
from ..shared.schemas import DdsRequest, DdsResponse
from .model import DdsBackend

settings = Settings()
model = DdsBackend(settings)
app = create_service_app(service_name="dds", model=model)


@app.post("/infer", response_model=DdsResponse, dependencies=[Depends(require_token)])
def infer(req: DdsRequest) -> DdsResponse:
    return model.infer(req)
