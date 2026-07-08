"""Wire contract shared by the 6DoF pose services.

Deliberately identical to the KIP `kip-pose-viewer` `/pose` contract so a future
orchestration gateway can fan out to either estimator interchangeably. Both
services return the *same* universal output: `T_cam_obj`, a 4x4 row-major
object->camera transform in the OpenCV camera frame (x right, y down, +z
forward), in **metres**.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PoseInstance(BaseModel):
    """One detected object to estimate a pose for."""

    model_config = ConfigDict(populate_by_name=True)

    id: int | str
    cls: str = Field(alias="class")  # object class name -> mesh / template lookup
    mask_b64: str  # PNG, single-channel 0/255


class PoseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rgb_b64: str  # PNG, uint8 RGB
    depth_b64: str | None = None  # PNG, uint16 MILLIMETRES (required for FoundationPose)
    K: list[float]  # flat 9, row-major [fx,0,cx, 0,fy,cy, 0,0,1]
    instances: list[PoseInstance]

    iterations: int = 5  # refine steps
    # --- GigaPose-only knobs (ignored by FoundationPose) ---
    hypotheses: int = 5
    pipeline: str = "rgbd"  # 'rgbd' | 'rgb' | '2d'
    kabsch: bool = True  # depth-align tail on the rgbd pipeline
    # --- 2D (planar) mode knob ---
    # Camera-frame table depth in metres, used by pipeline='2d' when per-mask
    # depth is unavailable. None -> fall back to a built-in default.
    plane_z: float | None = None


class ObjectPose(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int | str
    cls: str = Field(alias="class", serialization_alias="class")
    T_cam_obj: list[list[float]]  # 4x4
    score: float | None = None  # GigaPose provides this; FoundationPose does not
    stage: str | None = None  # 'coarse' | 'refined' | 'refined+kabsch' (GigaPose)


class PoseTimings(BaseModel):
    pose_ms: float
    num_posed: int


class PoseResponse(BaseModel):
    poses: list[ObjectPose]
    timings: PoseTimings


class PoseHealth(BaseModel):
    status: str
    service: str
    model: str
    device: str
    loaded: bool
    classes: list[str]
