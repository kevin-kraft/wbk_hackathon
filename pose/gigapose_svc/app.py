"""GigaPose service — FastAPI app on :8005. POST /pose (KIP-compatible).

Pipelines:
- 'rgbd'  : GigaPose coarse -> MegaPose refine -> Kabsch depth-align (needs depth).
- 'rgb'   : GigaPose coarse -> MegaPose refine, RGB only (still full 6DoF).
- '2d'    : CAD-free planar pose from the mask (centroid+depth -> 3D point,
            top-down + in-plane yaw). No templates / no model needed; fast
            fallback for flat, top-down picking. See shared/planar.py.

Unlike FoundationPose it returns a per-pose `score` and `stage`.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gigapose_svc.model import GigaPoseRunner
from shared.auth import require_token
from shared.imaging import K_from_flat, decode_depth_m, decode_mask, decode_rgb
from shared.planar import planar_pose
from shared.schemas import ObjectPose, PoseHealth, PoseRequest, PoseResponse, PoseTimings

runner = GigaPoseRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The 2D (planar) pipeline is model-free, so a missing/failed 6DoF model
    # must not stop the service from starting — it just disables 'rgb'/'rgbd'.
    try:
        runner.load()
    except Exception as e:  # noqa: BLE001 — report and degrade to 2D-only
        print(
            f"[gigapose] 6DoF model unavailable ({type(e).__name__}: {e}); "
            f"serving pipeline='2d' only",
            flush=True,
        )
    yield


app = FastAPI(title="pose-gigapose", lifespan=lifespan)
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
        service="gigapose",
        model=runner.name,
        device=runner.device,
        loaded=runner.loaded,
        classes=runner.classes,
    )


@app.post("/pose", response_model=PoseResponse, dependencies=[Depends(require_token)])
def pose(req: PoseRequest) -> PoseResponse:
    mode_2d = req.pipeline == "2d"
    use_depth = req.pipeline == "rgbd"
    if use_depth and not req.depth_b64:
        raise HTTPException(status_code=400, detail="pipeline='rgbd' requires depth_b64.")
    if not mode_2d and not runner.loaded:
        raise HTTPException(
            status_code=503,
            detail="6DoF model not loaded; use pipeline='2d' (mask-derived planar pose).",
        )

    # 2D mode uses depth (for z) when present but never requires it; the 6DoF
    # 'rgb' pipeline ignores depth; 'rgbd' consumes it in the Kabsch tail.
    rgb = decode_rgb(req.rgb_b64)
    depth = decode_depth_m(req.depth_b64) if req.depth_b64 else None
    K = K_from_flat(req.K)
    kabsch = req.kabsch and use_depth

    t0 = time.perf_counter()
    poses: list[ObjectPose] = []
    for inst in req.instances:  # serial: shared GPU context
        mask = decode_mask(inst.mask_b64)
        if mode_2d:
            T, score, stage = planar_pose(K, mask, depth, req.plane_z)
        else:
            T, score, stage = runner.estimate(
                inst.cls, K, rgb, mask, depth if use_depth else None,
                req.iterations, req.hypotheses, kabsch,
            )
        poses.append(
            ObjectPose(
                id=inst.id, **{"class": inst.cls}, T_cam_obj=T.tolist(), score=score, stage=stage
            )
        )
    pose_ms = (time.perf_counter() - t0) * 1000.0

    return PoseResponse(poses=poses, timings=PoseTimings(pose_ms=pose_ms, num_posed=len(poses)))


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": type(exc).__name__, "detail": str(exc)})
