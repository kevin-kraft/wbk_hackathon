# Architecture — VLM-Guided Robotic Disassembly

## Related Docs
- [System: Orchestrator](./orchestrator.md) — the state machine that ties every stage below together, the Protocol/client seam, loop states, the `/events/run` SSE endpoint
- [System: Dashboard](./dashboard.md) — the operator console / live demo UI that streams from the orchestrator
- [System: Robot Control](./robot_control.md) — the movement stage: Group 2's Jetson bridge to the LARA5 robot
- [System: Training](./training.md) — the custom YOLOv26 detection/segmentation training pipeline that feeds Stage 1 Perception's `yolo` and `yoloseg` services
- [Integration Points & Wire Contracts](./integration_points.md) — the base64-in-JSON contracts, model-adapter pattern, HF cache mount, the SSE contract
- [ADR: perception shared container vs. pose split containers](../Decisions/0001-perception-shared-container-pose-split-containers.md)
- [ADR: perception model stack](../Decisions/0002-perception-model-stack.md)
- [ADR: damage fail-safe sort policy](../Decisions/0003-damage-failsafe-sort-policy.md)
- [ADR: pose contract reuses kip-pose-viewer](../Decisions/0004-pose-contract-reuses-kip-pose-viewer.md)
- [ADR: mock-first, interface-seam integration](../Decisions/0005-mock-first-interface-seam-integration.md) — how the orchestrator runs the full loop today against mocks for teammate-owned pieces
- [ADR: dashboard is a separate static app](../Decisions/0008-frontend-separate-static-app.md) — why the UI isn't fused into the orchestrator
- [ADR: shared-token auth](../Decisions/0009-shared-token-auth.md) — the optional `WBK_API_TOKEN` gate on every work endpoint
- [ADR: robot_control integration](../Decisions/0010-robot-control-integration.md) — merging in Group 2's Jetson bridge as the movement stage, and the still-open orchestrator adapter gap
- [ADR: LLM action selector, constrained vocabulary](../Decisions/0011-llm-action-selector-constrained-vocabulary.md) — the guardrail on the plan-driven loop's optional LLM command synthesis
- [ADR 0015: YOLO-Seg sidecar container, no rebuild](../Decisions/0015-yoloseg-sidecar-container-no-rebuild.md) — why the new `yoloseg` service deploys as a second container on the GPU server instead of a `wbk-perception` image rebuild
- [SOP: running the services](../SOP/running_services.md)
- [SOP: running the tests](../SOP/running_tests.md)
- [SOP: running the orchestrator dry-run](../SOP/running_orchestrator_dry_run.md)
- [SOP: deploying perception to a remote GPU server](../SOP/deploy_perception_gpu_server.md) — deployed and running (2026-07-08); tunneled to a local orchestrator via `docker-compose.remote-gpu.yml`
- [ADR 0012: mask-derived detection labels](../Decisions/0012-mask-derived-detection-labels.md) — why YOLO detection training uses `--task detmask` instead of the `bbox_2d` annotator
- [ADR 0013: AMP disabled on the Blackwell training stack](../Decisions/0013-amp-disabled-blackwell-training.md)
- [ADR 0014: robot target selection (real \| sim \| both)](../Decisions/0014-robot-target-real-sim-both.md) — driving the Isaac Sim digital twin instead of/alongside the real arm, and why sim is a mirror, not a peer
- [ADR 0016: GigaPose 2D (planar) pose mode](../Decisions/0016-gigapose-2d-planar-pose-mode.md) — CAD-free, model-free pose from a mask, why it exists, and the graceful-degrade startup change (now wired into the orchestrator, see the ADR's 2026-07-08 update)
- [SOP: deploying the pose services (podman)](../SOP/deploy_pose_podman.md) — the `wbk-gigapose`/`wbk-foundationpose` podman deployment (distinct from perception's docker deployment), required auth, and the no-CAD-templates reality
- [ADR 0017: gray-world white balance + lowered detection confidence](../Decisions/0017-grayworld-white-balance-sim-to-real.md) — the sim-to-real fixes found debugging the live rig, and the durable-fix caveat (fine-tuning on real data, still open)
- [ADR 0018: durable `wbk-perception` redeploy](../Decisions/0018-durable-wbk-perception-redeploy.md) — bind-mounted source, restart policy, trimmed supervisord config for the GPU-server deployment
- `contracts/simulation_api.md` / `contracts/sim_scene_capture.md` — the Isaac Sim command-bus surface, and the (draft, unimplemented) sim scene-capture contract

## What this is

A hackathon project (WBK Hackathon Group, started 2026-07-07) building a robot
arm that disassembles a part step by step, guided by vision-language models in
the loop. Three product jobs, in order:

1. **Identify the next part to disassemble** — locate/point to the next
   component in the correct removal sequence.
2. **Rectify grabbing mistakes** — verify the grip after a pick attempt;
   detect and retry/correct if the wrong part (or nothing) was grabbed.
3. **Quality inspection (OK / not-OK)** — after removal, judge each part as OK
   or damaged and sort it into a working bin or reject bin.

Source of truth for the high-level pitch: repo-root [`README.md`](../../README.md)
and [`docs/architecture.md`](../../docs/architecture.md) — this doc adds the
implementation-level detail (ports, containers, code layout) on top of those.

## Pipeline

```
                       PLANNING HEAD (optional — plan mode only, see below)
                       ERP dataset ─► [LLM re-order+describe] ─► Plan (ordered steps)
                                             │
                                             ▼
              ┌────────────────  ORCHESTRATOR  (state machine, :8000) ────────────────┐
              ▼                                                                       │
 scene cam ─► PERCEPTION ─► 6DoF POSE ─► GRASP PLANNING ─► MOVEMENT ─► [grip sensor] ─► DAMAGE ─► bin
              (yolo/sam3/    (foundation   (naive/future,   (robot_control   (0/1 rectify,    (OpenRouter
               locate)        pose/giga)   optional LLM      :9000, built,    external)         VLM)   └─► loop back to PERCEPTION
                                            action selector,  adapter TODO)                              (fixed mode) or next
                                            constrained            │                                     plan step (plan mode)
                                            vocabulary)             ▼ ROBOT_TARGET=sim|both (mirrored, best-effort)
                                                          Isaac Sim digital twin (:8100, external —
                                                          IsaacSimMovement adapter, see ADR 0014)

                                     ▲ GET /events/run (SSE, read-only)
                                     │
                             DASHBOARD (frontend/, :5173, separate static app)
```

The **planning head** (`orchestrator/clients/erp.py` + `clients/llm_planner.py`,
added 2026-07-08) is an alternative front end to the loop, not a new stage in
the per-part pipeline: `run(product=...)` generates an ordered `Plan` once
up front (from a mock-ERP JSON dataset, optionally LLM re-ordered), then
drives the same PERCEPTION→POSE→GRASP→MOVEMENT→DAMAGE sequence per plan step
instead of per `perception.next_part()` call. See
[System: Orchestrator](./orchestrator.md) "Plan mode" and
[ADR 0011](../Decisions/0011-llm-action-selector-constrained-vocabulary.md)
(the constrained-vocabulary guardrail on the optional LLM action selector
inside GRASP PLANNING/MOVEMENT).

**MOVEMENT can also drive an Isaac Sim digital twin** instead of, or
mirrored alongside, the real Jetson arm — `ROBOT_TARGET=real|sim|both`
(default `real`, overridable per-run via `?target=`), resolved in
`orchestrator/factory.py:_build_robot()`. `both` mode fans every command out
to the real arm (authoritative) and the sim (best-effort mirror via
`TeeMovement` — a sim fault never fails a real run). See
[System: Orchestrator](./orchestrator.md) "Robot target selection" and
[ADR 0014](../Decisions/0014-robot-target-real-sim-both.md). This is
independent of the planning head above — either loop mode (fixed or
plan-driven) can run against `real`, `sim`, or `both`.

The **orchestrator** (`orchestrator/`, added `3abc923`) is the state machine
that drives this whole loop, calling each stage through pluggable clients —
see [System: Orchestrator](./orchestrator.md) for the loop states and the
Protocol seam, and [ADR 0005](../Decisions/0005-mock-first-interface-seam-integration.md)
for why it runs today against mocks for the pieces still in progress. The
**dashboard** (`frontend/`) is a separate static app that only *observes* the
loop over the orchestrator's `/events/run` SSE stream — it cannot drive the
robot through any path the loop itself doesn't expose — see
[System: Dashboard](./dashboard.md) and
[ADR 0008](../Decisions/0008-frontend-separate-static-app.md).

| Stage | Dir | Services (port) | Containers | Hardware | Status |
|---|---|---|---|---|---|
| Planning head (ERP + LLM) | `orchestrator/clients/erp.py`, `clients/llm_planner.py` | — (in-process; consumed via orchestrator `:8000`) | — | CPU (OpenRouter API call if LLM mode) | Built — mock-ERP JSON, optional LLM re-ordering, static fallback |
| Orchestrator | `orchestrator/` | orchestrator `:8000` | 1 | CPU | Built (mock-driven; also drives real services; SSE live-run endpoint; fixed + plan-driven modes) |
| Perception | `perception/` | yolo `:8001`, sam3 `:8002`, locateanything `:8003` | 1 (supervisord) | GPU | Built |
| 6DoF pose | `pose/` | foundationpose `:8004`, gigapose `:8005` | 2 (siblings) | GPU | Built |
| Grasp planning | `orchestrator/clients/naive_grasp.py` | — (in-process) | — | CPU | Naive placeholder — real module not built |
| Movement | `robot_control/` | robot_control `:9000` (Jetson) | 1 | CPU (drives LARA5 arm) | Service built + deployed (Group 2) — [System doc](./robot_control.md), [ADR 0010](../Decisions/0010-robot-control-integration.md) — orchestrator adapter to its real API **not yet written** |
| Simulator (digital twin) | `orchestrator/clients/sim_movement.py`, `clients/tee_movement.py` (adapter, in-repo) + external Isaac Sim backend | simulator `:8100` (external, KIT `ki_robotik_cv_seminar`, normally on-prem `kip-ws`) | 0 (adapter is in-process) | GPU (external, Isaac Sim) | Adapter built — arm motion + gripper only (`ROBOT_TARGET=sim\|both`, [ADR 0014](../Decisions/0014-robot-target-real-sim-both.md)); scene capture from the sim is a separate, unimplemented draft (`contracts/sim_scene_capture.md`); named-pose teach table is placeholder data |
| Grip detection | — | pressure sensor (external) | — | — | Teammate-owned, in progress — [proposed contract](../../contracts/grip_api.md); sim mode substitutes `SimGrip` (assume-grasp) |
| Damage inspection | `damage/` | damage `:8006` | 1 | CPU | Built |
| Dashboard (UI) | `frontend/` | dashboard `:5173` (nginx) | 1 | — | Built — live SSE, works today against mocks |

Grasp planning now has a working (if deliberately naive) placeholder in this
repo, and movement/grip detection now have proposed wire contracts and real
HTTP clients (`orchestrator/clients/http_movement.py`,
`orchestrator/clients/http_grip.py`) written against them. **Movement has
since landed as an actual service** — `robot_control/` (Group 2's Jetson
bridge, see [System: Robot Control](./robot_control.md)) is built, deployed
in both `docker-compose.yml` and `deploy/robot-control/`, and reachable — but
its real API (`/robot/hover/*`, `/robot/execute/`, `/robot/raw`) doesn't
match the draft `contracts/movement_api.md` shape `HttpMovement` calls, so
the orchestrator **still cannot drive it** until that adapter is written
(see [ADR 0010](../Decisions/0010-robot-control-integration.md)). The grip
sensor endpoint is still fully external/teammate-owned and not yet online.
See [System: Orchestrator](./orchestrator.md) "Teammate-owned contracts" and
"Two future VLM roles" for exactly what is and isn't built.

All stages are wired together in [`docker-compose.yml`](../../docker-compose.yml)
at the repo root (one `services:` entry per container: `orchestrator`,
`perception`, `foundationpose`, `gigapose`, `damage`).

## Stage 1 — Perception (`perception/`)

Three **independent FastAPI apps in one CUDA container**, run as separate
processes under `supervisord` (see [`perception/supervisord.conf`](../../perception/supervisord.conf)).
Each is its own `uvicorn` process on its own port — this is a deliberate
choice so any one service can be lifted into its own container later without
a rewrite (see ADR 0001).

`perception/Dockerfile`'s base image is parametrized via `ARG BASE_IMAGE`
(default `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`, commit `5fbacdf`) —
Blackwell GPUs (sm_120, e.g. RTX PRO 6000) need it overridden to a CUDA
12.8/torch 2.8 base at build time. `requirements.txt` deliberately excludes
torch so the base image's own build is used untouched. See
[SOP: deploying perception to a remote GPU server](../SOP/deploy_perception_gpu_server.md)
for the full recipe — this is now a **deployed, running** setup (two
containers, `wbk-perception` + a standalone `wbk-sam3`, reached via an SSH
tunnel), not just a local `docker compose` build.

The `yolo` service now serves a **custom-trained** detector
(`parts_detmask.pt`, 18 native part classes, mAP50 0.99 / recall 0.99)
instead of the stock `yolo11n.pt` default — trained on synthetic Isaac-Sim
data by the pipeline in `training/`. See [System: Training](./training.md)
for the training pipeline itself, and
[ADR 0012](../Decisions/0012-mask-derived-detection-labels.md) /
[ADR 0013](../Decisions/0013-amp-disabled-blackwell-training.md) for the two
training decisions behind that result.

A fourth perception service, **`yoloseg`** (added 2026-07-08, commit
`27fee6c`), serves the trained `parts_seg_v1` instance-segmentation model —
boxes, per-instance masks, and part labels in one pass, closed-vocabulary
over the same 18 classes. It's the closed-vocab counterpart to `yolo`
(detection-only): both are trained-parts models with no prompt, unlike
`sam3`/`locateanything`'s open-vocab text prompting.

| Service | Port | Job | Backend | Module |
|---|---|---|---|---|
| `yolo` | 8001 | object detection (closed-vocab, trained parts model) | Ultralytics YOLO (`YOLO_WEIGHTS`, default `yolo11n.pt`, deployed: `parts_detmask.pt`) | `perception/services/yolo/model.py` |
| `yoloseg` | 8007 | instance segmentation — boxes + per-instance masks + labels (closed-vocab, trained parts model) | Ultralytics YOLO-seg (`YOLO_SEG_WEIGHTS`, default `yolo11n-seg.pt`, deployed: `parts_seg.pt`), `predict(..., retina_masks=True)` for full-res masks | `perception/services/yoloseg/model.py` |
| `sam3` | 8002 | promptable segmentation (point/box + text/concept) | Meta SAM 3, `facebook/sam3` via `transformers` (gated weights) | `perception/services/sam3/model.py` |
| `locateanything` | 8003 | text-prompted localization/pointing | NVIDIA `LocateAnything-3B` via `trust_remote_code` | `perception/services/locateanything/model.py` |

`yoloseg`'s wire contract (`YoloSegRequest`/`SegInstance`/`YoloSegResponse` in
`perception/services/shared/schemas.py`) mirrors `yolo`'s shape plus a mask:
each `SegInstance` carries a `box` (`BBox`), a single-channel PNG mask
(`mask_b64_png`, via the existing `encode_mask_png_b64` helper — same
encoding `sam3` uses), `score`, `class_id`, and `label`. `retina_masks=True`
on the Ultralytics `.predict()` call is what makes the mask line up 1:1 with
the original image resolution instead of the model's letterboxed input size
— without it the frontend's `SceneView` overlay would need its own rescale
step.

**Gotcha, fixed 2026-07-08 (commit `4b6d1d3`):** the shared
`encode_mask_png_b64` helper (`perception/services/shared/imaging.py`)
skipped its 0/255 binarization step whenever the input array was already
`dtype=uint8` — but Ultralytics `result.masks.data` yields a uint8 mask with
values `{0,1}`, not `{0,255}`. Every mask consumer (the dashboard's overlay,
`gigapose`'s `pipeline='2d'`) thresholds at `> 127`, so those 0/1 masks read
as **entirely empty**: the YOLO-Seg overlay rendered blank, and 2D-mode pose
requests raised "empty mask". The fix always binarizes
(`(mask > 0).astype(uint8) * 255`, idempotent for already-0/255 inputs) — see
[System: Integration Points](./integration_points.md) for the shared-helper
detail. `sam3` uses the same encoder from a separate service image
(`wbk-sam3`) and picks up the fix on its next rebuild/redeploy, not
automatically.

On the GPU-server deployment, `yoloseg` runs as its own sidecar container
(`wbk-yoloseg`, host port `6770`) rather than inside `wbk-perception` —
see [ADR 0015](../Decisions/0015-yoloseg-sidecar-container-no-rebuild.md)
and [SOP: deploying perception to the GPU
server](../SOP/deploy_perception_gpu_server.md) for why and the full port
map. Locally (`docker-compose.yml`, single-host), it's a fourth
`supervisord` program inside the one shared `perception` container, same as
the other three — see [ADR 0001](../Decisions/0001-perception-shared-container-pose-split-containers.md).

Shared code lives in `perception/services/shared/`:
- `schemas.py` — request/response Pydantic models (`ImageInput`, `BBox`, `Point`,
  per-service request/response types). Geometry types (`BBox`, `Point`) are
  deliberately model-agnostic so downstream stages don't care which model
  produced a hit.
- `imaging.py` — `decode_image_b64` / `to_numpy` / `encode_mask_png_b64`.
- `config.py` — `Settings` dataclass (env-var driven) + `resolve_device`
  (falls back CUDA→CPU if unavailable).
- `model_base.py` — `BasePerceptionModel` abstract base every adapter subclasses.
- `app_factory.py` — `create_service_app()`: builds the FastAPI app with a
  startup lifespan that calls `model.load()` once, a `/health` route, a `/`
  info route, and a uniform exception handler.

SAM 3 detail worth knowing: the `transformers` integration exposes it as **two
separate model/processor pairs** — `Sam3Model`/`Sam3Processor` (concept/text
head, segments all matching instances) and `Sam3TrackerModel`/`Sam3TrackerProcessor`
(classic point/box head). `Sam3Backend.load()` in
`perception/services/sam3/model.py` loads both.

LocateAnything detail worth knowing: the model emits `<box><a><b><c><d></box>`
(4 ints, box) or `<box><a><b></box>` (2 ints, point) tokens with values
normalized to `[0,1000]`, not JSON. There is no native per-instance confidence
— `LocateAnythingBackend._parse()` in
`perception/services/locateanything/model.py` derives a rank-based pseudo-score
from Parallel Box Decoding order.

**Gotcha, fixed 2026-07-08 (commit `fcc2773`):** `LocateAnythingBackend`'s
`.generate()` call omitted `use_cache=True`, which the custom
`nvidia/LocateAnything-3B` model's own `generate()` implementation asserts —
every `POST /infer` against `locateanything` 500'd. Compounding this: the
shared `app_factory.py` exception handler for a bare `Exception` runs in
Starlette's `ServerErrorMiddleware`, **above** the CORS middleware in the
stack, so its 500 response never carried an `Access-Control-Allow-Origin`
header — the browser reported it as an opaque network error, not an HTTP
500, which is what made this take longer to diagnose than a normal 500
would have. Both are fixed: `use_cache=True` is now passed
(`perception/services/locateanything/model.py`), and the handler
(`perception/services/shared/app_factory.py:create_service_app`) now adds
`Access-Control-Allow-Origin: *` to every error response it returns, so
future service-side 500s surface as real HTTP 500s in the browser instead
of a CORS-blocked network error. See [System: Integration
Points](./integration_points.md) for the shared-handler detail.

Runtime import root: `perception/` itself (`uvicorn services.<name>.main:app`,
cwd=`/app/perception` per the Dockerfile/supervisord). See
[`tests/conftest.py`](../../tests/conftest.py) for why this matters for tests.

## Stage 2 — 6DoF Pose (`pose/`)

Estimates `T_cam_obj` (4x4, OpenCV camera frame, metres) per detected part.
**Two alternative estimators — not a coarse→refine chain** — each does its own
internal coarse→refine, and each lives in its **own container** because their
native dependency stacks conflict (see ADR 0001).

| Service | Port | Model | Depth | Extra output | Module |
|---|---|---|---|---|---|
| `foundationpose` | 8004 | FoundationPose | required (RGB-D) | — | `pose/foundationpose_svc/model.py` (`FoundationPoseRunner`) |
| `gigapose` | 8005 | GigaPose (`rgb`/`rgbd`) or CAD-free planar (`2d`) | optional (`rgbd` pipeline; `2d` uses it opportunistically) | `score`, `stage` | `pose/gigapose_svc/model.py` (`GigaPoseRunner`), `pose/shared/planar.py` (`planar_pose`, `2d` only) |

Shared code lives in `pose/shared/`:
- `schemas.py` — `PoseRequest`/`PoseInstance`/`ObjectPose`/`PoseResponse`/`PoseHealth`.
  Deliberately identical to the KIP `kip-pose-viewer` reference contract (ADR 0004).
- `imaging.py` — rgb/depth/mask/K decode helpers.
- `planar.py` (added 2026-07-08, commit `79f9ffa`) — the CAD-free `pipeline='2d'`
  geometry: numpy-only, no model/templates. See "GigaPose `pipeline='2d'`" below.

### GigaPose `pipeline='2d'` — CAD-free, model-free planar pose

`gigapose`'s `POST /pose` gained a third `pipeline` value, `'2d'`, alongside
the existing `'rgb'`/`'rgbd'` 6DoF pipelines (`pose/gigapose_svc/app.py`,
`pose/shared/planar.py`, `pose/shared/schemas.py`). It back-projects each
mask's centroid to a 3D point (depth priority: per-mask median depth from
the depth image → caller-supplied `plane_z` (camera-frame table depth,
metres) → a built-in `default_z=0.5`m; `stage` in `{2d, 2d-plane,
2d-defaultz}` records which) and builds a top-down grasp orientation whose
in-plane yaw follows the mask's principal axis (PCA on the mask pixels).
Output is the **same** `T_cam_obj` contract the 6DoF pipelines return, so it
is a drop-in for the orchestrator/frontend — see [ADR
0016](../Decisions/0016-gigapose-2d-planar-pose-mode.md) for why this mode
exists (inspired by the KIP seminar's `detect_and_move`) and its trade-offs.

This matters today because **the deployed `wbk-gigapose` has no CAD
templates for this project's parts** (`GET /health`'s `classes` field
returns `[]`) — GigaPose's 6DoF pipelines need 162 pre-rendered templates
per object on disk before they can pose anything real, and those templates
don't exist for this project's parts yet. `pipeline='2d'` needs no
templates/CAD mesh/model load at all, so **it is currently the only pose
path that works against real parts** on the deployed instance; a
`pipeline='rgb'`/`'rgbd'` request against it 503s with an explicit
"6DoF model not loaded; use pipeline='2d'" message rather than the service
failing to serve anything. `gigapose_svc/app.py`'s startup lifespan wraps
`GigaPoseRunner.load()` in a try/except specifically so a missing/failed
6DoF model degrades the service to 2D-only instead of blocking startup
entirely. See [SOP: deploying the pose services
(podman)](../SOP/deploy_pose_podman.md) for the deployed reality and
[System: Integration Points](./integration_points.md) Contract 2 for the
full request/response shape.

**Wired into the orchestrator 2026-07-08 (commit `2485997`):** `HttpPose`
now sends `pipeline` (default `rgbd`, from `OrchestratorConfig.pose_pipeline`
/ env `POSE_PIPELINE`) and routes `2d`/`rgb` requests to a dedicated
`gigapose_url` instead of the FoundationPose-default `pose_url`. Overridable
per-run via `POST /run?pose_pipeline=` / `GET /events/run?pose_pipeline=`
(no restart needed), with a matching Pose selector in the dashboard's
`RunControls` — see [System: Orchestrator](./orchestrator.md) "Pose pipeline
selection" and [System: Dashboard](./dashboard.md). An operator can now
select `2D` end-to-end to get a real pose against real parts on the
currently-deployed GigaPose instance (which has no CAD templates for
`rgb`/`rgbd`). Real-robot grasp success using 2D-mode poses through the full
loop is still unverified — this closes the wiring gap only, see [ADR
0016](../Decisions/0016-gigapose-2d-planar-pose-mode.md)'s 2026-07-08
update.

Both services build on top of **pre-built GPU base images** (`foundationpose:blackwell`,
`gigapose:blackwell`) that must be compiled from the model repos first — see
[SOP: running the services](../SOP/running_services.md). Each service Docker
image then only adds FastAPI + the thin `app.py`/`model.py` layer on top.

Runtime import root: `pose/` (each container sets `PYTHONPATH=/svc`, copies
`shared/` and its own `<name>_svc/` into `/svc`).

## Stage 3 — Damage Inspection (`damage/`)

CPU-only (`python:3.11-slim` base, no GPU). The arm holds a removed part up to
a dedicated inspection webcam; multi-angle shots POST to `/inspect`. A VLM
reached via **OpenRouter** (default model `anthropic/claude-sonnet-5`, see
`damage/config.py`) compares the images against known-good/known-damaged
reference examples and returns a verdict.

Layout (`damage/`):
- `schemas.py` — `DamageRequest`, `DamageVerdict` (`verdict`/`damaged`/`confidence`/`bin`/`issues`/`reasoning`), `DamageHealth`.
- `config.py` — `Settings`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, `REFERENCE_DIR`, `DAMAGE_TIMEOUT_S`.
- `prompts.py` — system prompt + message builder (references first, then target images).
- `reference.py` — disk-backed per-class reference loader (`<REFERENCE_DIR>/<class>/{ok,damaged}/*`).
- `client.py` — OpenRouter `/chat/completions` call + JSON extraction from the model's reply.
- `app.py` — the FastAPI service (`:8006`); this is where the **bin-sort policy**
  is implemented (see ADR 0003) — `bin="ok_bin" if verdict == "ok" else "reject_bin"`.

Runtime import root: repo root (`damage/__init__.py` exists, run as package `damage`).

## Not yet built

As of the orchestrator addition (`3abc923`, 2026-07-07):

- **Real grasp planning** — `NaiveTopDownGrasp` (`orchestrator/clients/naive_grasp.py`)
  is a placeholder (top-down at the object origin, fixed stand-off, no
  gripper geometry). No real planning module exists yet.
- **Movement adapter** — the arm itself is no longer purely external: `robot_control/`
  (Group 2's Jetson bridge) is now a real, deployed service in this repo —
  see [System: Robot Control](./robot_control.md). But its API
  (`/robot/hover/*`, `/robot/execute/`) doesn't match the draft
  `contracts/movement_api.md` shape the orchestrator's `HttpMovement` client
  (`orchestrator/clients/http_movement.py`) calls, and the pose-vector/frame
  conventions needed to bridge them are unconfirmed — see
  [ADR 0010](../Decisions/0010-robot-control-integration.md) "Open gap". Do
  not assume the orchestrator can drive the real arm yet.
- **Grip-sensor hardware** — still fully external, teammate-owned. This repo
  has a real HTTP client (`orchestrator/clients/http_grip.py`) and a
  proposed contract (`contracts/grip_api.md`) for it, but the endpoint
  itself is not yet online — do not assume it is reachable.
- **YOLO detection tuning** for the specific disassembly-part vocabulary is
  now trained and deployed (`parts_detmask.pt`, 18 classes, mAP50 0.99/recall
  0.99 — see [System: Training](./training.md)) to the GPU-server
  `wbk-perception` container. The orchestrator's *mock* `next_part` path
  (mocks-first design, [ADR 0005](../Decisions/0005-mock-first-interface-seam-integration.md))
  is unaffected by this and still exists as the default for dry-runs/tests —
  this bullet is about the underlying model quality, not the orchestrator's
  client wiring.
- **Two VLM roles from the task spec** — VLM next-part selection (an
  alternative `PerceptionClient.next_part` backend) and VLM grip
  verification (a second opinion alongside the binary grip sensor). Both
  have a clean seam in the Protocol design but neither is implemented — see
  [System: Orchestrator](./orchestrator.md) "Two future VLM roles". (Not to
  be confused with the planning head and constrained-vocabulary action
  selector below, which **are** implemented — those are a different vision,
  captured and shipped 2026-07-08.)
- **Real ERP integration** — the planning head (see "Plan mode" above and
  [System: Orchestrator](./orchestrator.md)) is built against a mock JSON
  dataset (`orchestrator/data/erp_products.json`) behind a `PlanProvider`
  Protocol; a real ERP system was explicitly out of scope for the hackathon,
  and would implement the same Protocol with no loop changes.
- **Sim scene capture** — feeding perception/pose from a rendered Isaac Sim
  frame instead of the real Zivid. The sim backend's `GET_ZIVID_DATA`
  command is unimplemented and there is no HTTP route that returns an image;
  `contracts/sim_scene_capture.md` is a draft handoff to Group 2 (the
  rendering plumbing they'd reuse already exists elsewhere in their repo,
  just not wired into `simulation_backend`). Until it lands, `sim`/`both`
  robot-target runs still need the real Zivid (or `StaticSceneCamera`) for
  perception input — only the arm/gripper backend switches, see
  [ADR 0014](../Decisions/0014-robot-target-real-sim-both.md). The frontend
  dashboard's `SourceToggle`/`SceneView` already call the draft contract and
  degrade gracefully ("not implemented yet") until it exists — see
  [System: Dashboard](./dashboard.md).
- **Sim named-pose teach table** — `home`/`clearance`/`ok_bin`/`reject_bin`/
  `inspect_*` have no sim equivalent; `orchestrator/clients/sim_movement.py`'s
  built-in table and `deploy/sim_named_poses.example.json` are rough
  placeholders, not measured teach points (see
  [System: Orchestrator](./orchestrator.md) "Robot target selection").
- **Real-robot grasp success using GigaPose `pipeline='2d'`** — the CAD-free
  planar pose mode (see "Stage 2 — 6DoF Pose" above and [ADR
  0016](../Decisions/0016-gigapose-2d-planar-pose-mode.md)) is now wired
  into the orchestrator end-to-end (`pose_pipeline='2d'`, see [System:
  Orchestrator](./orchestrator.md) "Pose pipeline selection", shipped
  2026-07-08 commit `2485997`) and verified pose-service-side against real
  masks, but a full real-robot pick using a 2D-mode pose through the loop
  (grasp planning → movement → grip confirmation) has not been evaluated
  end-to-end. See [SOP: deploying the pose services
  (podman)](../SOP/deploy_pose_podman.md).
- **Real-frame fine-tuning for the parts detectors** — [ADR
  0017](../Decisions/0017-grayworld-white-balance-sim-to-real.md)'s
  gray-world white balance and lowered confidence threshold are stopgaps for
  the sim-to-real gap (the models are trained 100% on synthetic Isaac-Sim
  renders); the durable fix — fine-tuning on real labelled frames — needs a
  real-frame dataset that doesn't exist yet and has not been started.

## Test suite

**Still 204** after the 2026-07-08 debugging/deployment session (commits
`fcc2773`, `2485997`, `7f12f41`) — no new tests were added for the
white-balance/conf/locateanything/CORS fixes ([ADR
0017](../Decisions/0017-grayworld-white-balance-sim-to-real.md)), the
pose-pipeline wiring ([ADR 0016](../Decisions/0016-gigapose-2d-planar-pose-mode.md)'s
update), or the `wbk-perception` redeploy script ([ADR
0018](../Decisions/0018-durable-wbk-perception-redeploy.md), infra-only, not
Python application code). All verification for this session was manual,
against the live rig/deployed services — see the ADRs above for the
specific before/after numbers each fix was checked against.

204 pytest tests (`tests/`), up from 105 before the ERP/LLM planning head
(2026-07-08): the prior 105 (86 covering pure logic in perception/pose/damage
— schemas, image/tensor codecs, the LocateAnything token parser, prompt
building, the damage bin policy, FastAPI route wiring with model adapters
mocked — plus the full disassembly loop end-to-end against mocks
(rectify-retry, reject-bin routing, blacklisting an ungraspable part,
bounded termination), plus 19 `test_auth.py` tests covering `require_token`
— see [ADR 0009](../Decisions/0009-shared-token-auth.md)) are unchanged and
still green, plus **24 new tests** in
[`tests/orchestrator/test_plan.py`](../../tests/orchestrator/test_plan.py)
covering the planning head end to end: the constrained action vocabulary's
full rejection surface, `StaticPlanProvider`/`LlmPlanProvider` (permutation
guardrail, static fallback on any LLM error), plan-driven loop behavior
(SKIP/BLOCKED/STEP/PLAN_GENERATED events), and the `/products`/`/plan`/
`product`-param endpoints — see [System: Orchestrator](./orchestrator.md)
"Plan mode" and [ADR 0011](../Decisions/0011-llm-action-selector-constrained-vocabulary.md).
The 204 total also already includes 22 further tests
(`tests/orchestrator/test_robot_target.py`, `test_sim_movement.py`) covering
the real/sim/both robot-target selection and the `IsaacSimMovement` command-
bus adapter — see [System: Orchestrator](./orchestrator.md) "Tests". No GPU,
no model weights, no `OPENROUTER_API_KEY` (the LLM clients are
tested via a monkeypatched `_chat()` seam, not a real network call), no
hardware. See [SOP: running the tests](../SOP/running_tests.md) for the
conftest.py per-stage import-root subtlety and what's intentionally NOT
covered (`*.load()`/`*.infer()`/`*.estimate()` on all five real model
adapters). This count is Python-only. `frontend/` has its own **Vitest**
unit suite — 30 tests across 4 files (`npm test` → `vitest run`, jsdom env,
`frontend/vitest.config.ts`), covering `config/runtime.ts`'s endpoint
precedence resolution, `lib/stages.ts`'s state→stage mapping, the
event-reducer logic in `lib/derive.ts` (`tallyBins`, `deriveInspections`,
`deriveGrip`, `currentPart`, and — 4 new cases as of 2026-07-08 —
`derivePlan`, which turns `PLAN_GENERATED`/`STEP`/`SORT`/`SKIP`/`BLOCKED`
events into the `PlanProgress` checklist), and the `apiToken`
auth-header/query-param wiring in `lib/api.ts` — see
[System: Dashboard](./dashboard.md) for detail. `npm run build`
(`tsc -b && vite build`) remains the type-check + production-bundle gate on
top of that.

CI: `.github/workflows/tests.yml` has two jobs. `pytest` runs `uv sync
--frozen && uv run pytest -q` (204 tests). `frontend` runs `npm ci`, then
`npm test` (the 30-test Vitest suite), then `npm run build` — so unit tests,
type-check, and build all gate every push/PR to `main`. Green as of
`7cf5211` ("Add GitHub Actions CI to run tests on push/PR to main"),
extended to cover the frontend suite once Vitest landed, again for the
shared-token auth tests, and again for the planning head.
