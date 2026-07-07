# Architecture

VLM/CV-guided robotic disassembly. The system removes parts from an assembly one
at a time; a vision layer decides *what* to remove next, estimates *where/how* it
sits, checks the arm *did* it, and finally judges whether each removed part is
**OK or damaged** — sorting it into the correct bin.

## Pipeline

```
                      ┌──────────────────────────────────────────────┐
   scene camera ────► │  PERCEPTION  (1 GPU container, 3 FastAPI apps) │
   (RGB / RGB-D)      │    yolo :8001   sam3 :8002   locate :8003     │
                      │    detect       segment      text→point       │
                      └───────────────┬──────────────────────────────┘
                                      │  next-part box / mask / point
                                      ▼
                      ┌──────────────────────────────────────────────┐
                      │  6DoF POSE   (2 GPU containers — incompatible  │
                      │              stacks, pick one per request)     │
                      │    foundationpose :8004   |   gigapose :8005   │
                      └───────────────┬──────────────────────────────┘
                                      │  T_cam_obj (4x4, metres)
                                      ▼
                      ┌──────────────────────────────────────────────┐
                      │  GRASP PLANNING  (future)                     │
                      │    pick target → grasp pose → verify grip     │
                      └───────────────┬──────────────────────────────┘
                                      │  grasp pose / trajectory goal
                                      ▼
                      ┌──────────────────────────────────────────────┐
                      │  MOVEMENT  (future)                           │
                      │    arm control · execute pick & remove        │
                      └───────────────┬──────────────────────────────┘
                                      │  removed part, held to webcam
                                      ▼
                      ┌──────────────────────────────────────────────┐
                      │  DAMAGE INSPECTION  (CPU — OpenRouter VLM)     │
                      │    damage :8006  → ok_bin | reject_bin        │
                      └──────────────────────────────────────────────┘
                                      │
                                      └──► loop: back to PERCEPTION for next part
```

An **orchestrator** (state machine, `orchestrator/`, :8000) drives this whole
loop, calling each stage through pluggable clients — so it runs today against
mocks for the pieces still in progress (YOLO detection, the Jetson **movement**
endpoint, the binary **grip sensor**). It owns the "rectify grabbing mistakes"
logic: the 0/1 grip sensor gates progress and a failed read re-plans and retries.

**Built now:** orchestrator (mock-driven), perception, 6DoF pose, damage inspection.
**In progress (teammates):** YOLO detection, Jetson movement endpoint, grip
sensor — proposed contracts in [`../contracts/`](../contracts/).
**Future:** a real grasp-planning module (naive placeholder for now), plus two
VLM roles the task calls for — **VLM next-part selection** (from a part
description/prompt; an alternative perception `next_part` backend) and **VLM grip
verification** (a visual check alongside the binary sensor). Neither implemented
yet; seams are noted in `orchestrator/README.md`.

## The three product jobs → which stages serve them

1. **Identify the next part** — `perception` (LocateAnything text→point and/or
   YOLO detection propose the next component; SAM3 segments it).
2. **Rectify grabbing mistakes** — SAM3 before/after segmentation + the 6DoF pose
   confirm the right part was gripped and removed; else the step retries.
3. **OK / not-OK (damaged)** — `damage` inspects each removed part and sorts it.

---

## Perception module — `perception/`

Three **independent FastAPI services** in **one CUDA container** under
`supervisord`. Separate apps (not one app with three routers) so any one can be
lifted into its own container later without a rewrite.

| Service | Port | Job | Backend |
|---|---|---|---|
| `yolo` | 8001 | detection — find candidate parts | Ultralytics YOLO |
| `sam3` | 8002 | promptable segmentation (point/box/text) | Meta **SAM 3** (`facebook/sam3`, gated) |
| `locateanything` | 8003 | text-prompted localization / pointing | NVIDIA **LocateAnything-3B** |

Contract: `POST /infer` (base64 image in JSON) + `GET /health` + `/docs`. Shared
geometry types (`BBox`, `Point`) so downstream stages don't care which model
produced a hit. Each loads its weights once at startup via a `BasePerceptionModel`
adapter. Details: [`../perception/README.md`](../perception/README.md).

## 6DoF pose module — `pose/`

Estimates `T_cam_obj` (4x4, OpenCV camera frame, metres) per detected part.
**Two alternative estimators**, each its own container (their native stacks —
numpy / xformers / panda3d / CUDA exts — conflict and cannot co-locate):

| Service | Port | Depth | Extra output |
|---|---|---|---|
| `foundationpose` | 8004 | required (RGB-D) | — |
| `gigapose` | 8005 | optional (`rgbd`/`rgb`) | `score`, `stage` |

Contract: `POST /pose` with `rgb_b64` + `depth_b64` (uint16 mm) + `K` (flat 9) +
`instances:[{id,class,mask_b64}]`. Mirrors the KIP `kip-pose-viewer` reference so
a future gateway can fan out to either. Each needs per-object CAD meshes (and
GigaPose needs pre-rendered templates). Details + fragile bits:
[`../pose/README.md`](../pose/README.md).

## Damage-inspection stage — `damage/`

CPU-only. The arm holds a removed part to a dedicated inspection webcam; the
multi-angle shots go to `POST /inspect`. A **VLM via OpenRouter** compares them
against known-good / known-damaged references (inline or disk-backed per class)
and returns `{verdict, damaged, confidence, bin, issues, reasoning}`. Policy:
only a clean `ok` → `ok_bin`; `damaged` and `uncertain` → `reject_bin`. Details:
[`../damage/README.md`](../damage/README.md).

---

## Design conventions across stages

- **Base64-in-JSON** wire contracts everywhere — no multipart, trivial
  service-to-service calls.
- **Thin web layer, fat adapter** — a `model.py` owns weight loading + inference;
  the FastAPI app just routes. Swapping a backend edits one file.
- **Load once at startup** (FastAPI lifespan), GPU-resident.
- **Each service is independently containerizable** — self-contained
  `model.py` / `app.py` / `requirements.txt`.

## Repo layout

```
perception/   YOLO + SAM3 + LocateAnything (1 GPU container, supervisord)
pose/         FoundationPose + GigaPose (2 GPU containers)
damage/       OpenRouter VLM damage inspection (CPU)
tests/        pytest suite (GPU/network-free, heavy layers mocked)
docs/         this file
docker-compose.yml   all stages as services
.github/workflows/tests.yml   CI: uv run pytest on push/PR to main
```

## CI & tests

The `tests/` suite runs the pure logic across all three stages (schemas, image
codecs, the LocateAnything token parser, damage bin policy, FastAPI route wiring)
with the heavy model/network layers mocked — no GPU, weights, or network needed.
`.github/workflows/tests.yml` runs it (`uv sync --frozen && uv run pytest`) on
every push and PR to `main`.
