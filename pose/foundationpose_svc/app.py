"""FoundationPose service — FastAPI app on :8004. POST /pose (KIP-compatible)."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from foundationpose_svc.model import FoundationPoseRunner
from shared.auth import require_token
from shared.imaging import K_from_flat, decode_depth_m, decode_mask, decode_rgb
from shared.schemas import ObjectPose, PoseHealth, PoseRequest, PoseResponse, PoseTimings

runner = FoundationPoseRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner.load()
    yield


app = FastAPI(title="pose-foundationpose", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=PoseHealth)
def health() -> PoseHealth:
    return PoseHealth(
        status="ok" if runner.loaded else "loading",
        service="foundationpose",
        model=runner.name,
        device=runner.device,
        loaded=runner.loaded,
        classes=runner.classes,
    )


@app.post("/pose", response_model=PoseResponse, dependencies=[Depends(require_token)])
def pose(req: PoseRequest) -> PoseResponse:
    if not req.depth_b64:
        raise HTTPException(status_code=400, detail="FoundationPose requires depth (depth_b64).")

    rgb = decode_rgb(req.rgb_b64)
    depth = decode_depth_m(req.depth_b64)
    K = K_from_flat(req.K)

    t0 = time.perf_counter()
    poses: list[ObjectPose] = []
    for inst in req.instances:  # serial: shared GL context is not thread-safe
        mask = decode_mask(inst.mask_b64)
        T = runner.estimate(inst.cls, K, rgb, depth, mask, req.iterations)
        poses.append(ObjectPose(id=inst.id, **{"class": inst.cls}, T_cam_obj=T.tolist()))
    pose_ms = (time.perf_counter() - t0) * 1000.0

    return PoseResponse(
        poses=poses,
        timings=PoseTimings(pose_ms=pose_ms, num_posed=len(poses)),
    )


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": type(exc).__name__, "detail": str(exc)})
