"""Scene-camera capture service — FastAPI on :9002.

Captures an RGB-D frame from the Zivid (fixed, eye-to-hand scene camera on the
Jetson) and returns it in the orchestrator's `SceneFrame` shape so it drops
straight into the `SceneCamera` seam (POST /capture). This is the SCENE camera
for perception + 6DoF pose — NOT the inspection webcam the damage VLM uses.
"""

from __future__ import annotations

import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import require_token
from .backend import make_backend
from .config import Settings
from .imaging import encode_depth_mm_b64, encode_rgb_b64
from .schemas import SceneCaptureResponse, SceneHealth

settings = Settings()
backend = make_backend(settings)

app = FastAPI(title="scene-camera")

# Let the dashboard poll /health from the browser (auth still gates /capture).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=SceneHealth)
def health() -> SceneHealth:
    return SceneHealth(status="ok", backend=backend.name, ready=backend.ready)


@app.post("/capture", response_model=SceneCaptureResponse, dependencies=[Depends(require_token)])
def capture() -> SceneCaptureResponse:
    t0 = time.perf_counter()
    cap = backend.capture()
    h, w = cap.rgb.shape[:2]
    return SceneCaptureResponse(
        rgb_b64=encode_rgb_b64(cap.rgb),
        depth_b64=(
            encode_depth_mm_b64(cap.depth_mm, max_mm=settings.depth_max_mm)
            if cap.depth_mm is not None
            else None
        ),
        K=cap.K,
        width=w,
        height=h,
        backend=backend.name,
        capture_ms=(time.perf_counter() - t0) * 1000.0,
    )


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(status_code=500, content={"error": type(exc).__name__, "detail": str(exc)})
