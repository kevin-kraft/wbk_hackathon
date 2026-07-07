# 6DoF pose module

The pose stage estimates a full 6DoF pose (`T_cam_obj`, 4x4, OpenCV camera frame,
metres) for each detected part, so the grasp planner knows *where* and *how* the
part is oriented. It wraps two alternative estimators — pick one per request:

| Service | Port | Model | Depth | Extra output |
|---|---|---|---|---|
| `foundationpose` | 8004 | FoundationPose | **required** (RGB-D) | — |
| `gigapose` | 8005 | GigaPose | optional (`rgbd` vs `rgb` pipeline) | `score`, `stage` |

They are **alternatives, not a coarse→refine chain** — each does its own internal
coarse→refine. This mirrors the reference implementation in `~/code/kip-pose-viewer`.

## Two containers, on purpose

FoundationPose and GigaPose **cannot share one container**: their native stacks
conflict (FoundationPose needs `numpy>=2` + pybind11 for its C++ pose-clustering
ext; GigaPose pins `numpy<2` and brings xformers/panda3d/MegaPose). So the 6DoF
*stage* is two sibling service containers, each built on its own heavy GPU base
image. (Contrast the perception module, where three light models happily share
one container.)

## Wire contract (shared by both)

`POST /pose` — base64-in-JSON:

```jsonc
{
  "rgb_b64":   "<PNG uint8 RGB>",
  "depth_b64": "<PNG uint16 MILLIMETRES>",   // required for foundationpose
  "K":         [fx,0,cx, 0,fy,cy, 0,0,1],    // flat 9, row-major
  "instances": [{"id": 0, "class": "housing", "mask_b64": "<PNG 0/255>"}],
  "iterations": 5,
  // gigapose-only:
  "hypotheses": 5, "pipeline": "rgbd", "kabsch": true
}
```

Response: `{"poses": [{"id","class","T_cam_obj":[[4x4]],"score?","stage?"}], "timings": {...}}`.

Also `GET /health` → `{status, service, model, device, loaded, classes}`.

Contract lives in [`shared/schemas.py`](shared/schemas.py); it is deliberately
identical to KIP's so a future orchestration gateway can fan out to either
estimator interchangeably.

## Build & run

Both services build **on top of GPU base images** that must be built first from
the model repos (they compile CUDA extensions — slow, GPU-arch-specific):

```bash
# 1. base images (from the model repos in ~/code) — retag arch as needed
docker build -t foundationpose:blackwell -f ~/code/FoundationPose/docker/Dockerfile.blackwell ~/code/FoundationPose
docker build -t gigapose:blackwell        -f ~/code/GigaPose/docker/Dockerfile.blackwell        ~/code/GigaPose

# 2. then the service images + run (from repo root)
docker compose up --build foundationpose gigapose
```

Requires an NVIDIA GPU + Container Toolkit. The model repos are **mounted** into
the containers (see `docker-compose.yml`) so weights, meshes, and GigaPose
templates come from disk.

## Per-object setup (the parts you must supply)

The reference KIP hardcodes two demo parts. For your disassembly objects:

- **FoundationPose** — a CAD mesh per class (`.obj`, **in metres**) in `FP_MESH_DIR`,
  and a `FP_CLASS_MESH` map, e.g. `{"housing":"housing.obj","bracket":"bracket.obj"}`.
- **GigaPose** — a CAD mesh per class **and 162 pre-rendered templates per object**
  on disk *before* the service starts (rendered by GigaPose's
  `render_custom_templates.py`). The class→objId map lives in the KIP
  `gigapose_infer` adapter.

## Configuration (env vars)

| Var | Service | Default | Purpose |
|---|---|---|---|
| `FP_REPO` | fp | `/workspace/FoundationPose` | FoundationPose repo path (mounted) |
| `FP_MESH_DIR` | fp | `/meshes` | dir of `.obj` meshes (metres) |
| `FP_CLASS_MESH` | fp | `{}` | JSON map class→mesh filename |
| `FP_ITERATIONS` | fp | `5` | default refine steps |
| `GIGAPOSE_REPO` | gp | `/workspace/GigaPose` | GigaPose repo path (mounted) |
| `GP_DATASET` | gp | `kip2` | dataset/template set name |
| `GP_ENABLE_REFINER` | gp | `1` | MegaPose refiner on/off |

## Fragile bits (from the KIP reference)

- FoundationPose is **~2 s/instance, serial** (shared non-thread-safe GL context) —
  cap instances with the caller's `top_n`.
- Depth must be **metric uint16 mm**; GigaPose does subtle mm↔m handling internally.
- GigaPose templates must be pre-rendered and correctly scaled or coarse matching
  silently degrades.
- Base images are **sm_120/Blackwell-specific**; change `TORCH_CUDA_ARCH_LIST` for
  other GPUs.

## Layout

```
shared/               schemas (wire contract) + imaging (rgb/depth/mask/K decode)
foundationpose_svc/   model.py (FoundationPoseRunner) + app.py (:8004) + Dockerfile
gigapose_svc/         model.py (GigaPoseRunner)       + app.py (:8005) + Dockerfile
```
