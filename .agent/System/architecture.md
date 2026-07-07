# Architecture — VLM-Guided Robotic Disassembly

## Related Docs
- [System: Orchestrator](./orchestrator.md) — the state machine that ties every stage below together, the Protocol/client seam, loop states, the `/events/run` SSE endpoint
- [System: Dashboard](./dashboard.md) — the operator console / live demo UI that streams from the orchestrator
- [Integration Points & Wire Contracts](./integration_points.md) — the base64-in-JSON contracts, model-adapter pattern, HF cache mount, the SSE contract
- [ADR: perception shared container vs. pose split containers](../Decisions/0001-perception-shared-container-pose-split-containers.md)
- [ADR: perception model stack](../Decisions/0002-perception-model-stack.md)
- [ADR: damage fail-safe sort policy](../Decisions/0003-damage-failsafe-sort-policy.md)
- [ADR: pose contract reuses kip-pose-viewer](../Decisions/0004-pose-contract-reuses-kip-pose-viewer.md)
- [ADR: mock-first, interface-seam integration](../Decisions/0005-mock-first-interface-seam-integration.md) — how the orchestrator runs the full loop today against mocks for teammate-owned pieces
- [ADR: dashboard is a separate static app](../Decisions/0008-frontend-separate-static-app.md) — why the UI isn't fused into the orchestrator
- [ADR: shared-token auth](../Decisions/0009-shared-token-auth.md) — the optional `WBK_API_TOKEN` gate on every work endpoint
- [SOP: running the services](../SOP/running_services.md)
- [SOP: running the tests](../SOP/running_tests.md)
- [SOP: running the orchestrator dry-run](../SOP/running_orchestrator_dry_run.md)
- [SOP: deploying perception to a remote GPU server](../SOP/deploy_perception_gpu_server.md) — in progress, not yet running

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
              ┌────────────────  ORCHESTRATOR  (state machine, :8000) ────────────────┐
              ▼                                                                       │
 scene cam ─► PERCEPTION ─► 6DoF POSE ─► GRASP PLANNING ─► MOVEMENT ─► [grip sensor] ─► DAMAGE ─► bin
              (yolo/sam3/    (foundation   (naive/future)   (Jetson,     (0/1 rectify)   (OpenRouter
               locate)        pose/giga)                     external)                    VLM)   └─► loop back to PERCEPTION

                                     ▲ GET /events/run (SSE, read-only)
                                     │
                             DASHBOARD (frontend/, :5173, separate static app)
```

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
| Orchestrator | `orchestrator/` | orchestrator `:8000` | 1 | CPU | Built (mock-driven; also drives real services; SSE live-run endpoint) |
| Perception | `perception/` | yolo `:8001`, sam3 `:8002`, locateanything `:8003` | 1 (supervisord) | GPU | Built |
| 6DoF pose | `pose/` | foundationpose `:8004`, gigapose `:8005` | 2 (siblings) | GPU | Built |
| Grasp planning | `orchestrator/clients/naive_grasp.py` | — (in-process) | — | CPU | Naive placeholder — real module not built |
| Movement | — | Jetson endpoint (external) | — | — | Teammate-owned, in progress — [proposed contract](../../contracts/movement_api.md) |
| Grip detection | — | pressure sensor (external) | — | — | Teammate-owned, in progress — [proposed contract](../../contracts/grip_api.md) |
| Damage inspection | `damage/` | damage `:8006` | 1 | CPU | Built |
| Dashboard (UI) | `frontend/` | dashboard `:5173` (nginx) | 1 | — | Built — live SSE, works today against mocks |

Grasp planning now has a working (if deliberately naive) placeholder in this
repo, and movement/grip detection now have proposed wire contracts and real
HTTP clients (`orchestrator/clients/http_movement.py`,
`orchestrator/clients/http_grip.py`) written against them — but the arm and
sensor endpoints themselves are external, teammate-owned, and not yet online.
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
(in progress, not yet running) for the full recipe.

| Service | Port | Job | Backend | Module |
|---|---|---|---|---|
| `yolo` | 8001 | object detection | Ultralytics YOLO (`YOLO_WEIGHTS`, default `yolo11n.pt`) | `perception/services/yolo/model.py` |
| `sam3` | 8002 | promptable segmentation (point/box + text/concept) | Meta SAM 3, `facebook/sam3` via `transformers` (gated weights) | `perception/services/sam3/model.py` |
| `locateanything` | 8003 | text-prompted localization/pointing | NVIDIA `LocateAnything-3B` via `trust_remote_code` | `perception/services/locateanything/model.py` |

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
| `gigapose` | 8005 | GigaPose | optional (`rgbd`/`rgb` pipeline) | `score`, `stage` | `pose/gigapose_svc/model.py` (`GigaPoseRunner`) |

Shared code lives in `pose/shared/`:
- `schemas.py` — `PoseRequest`/`PoseInstance`/`ObjectPose`/`PoseResponse`/`PoseHealth`.
  Deliberately identical to the KIP `kip-pose-viewer` reference contract (ADR 0004).
- `imaging.py` — rgb/depth/mask/K decode helpers.

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
- **Movement (Jetson arm) and grip-sensor hardware** — both are external,
  teammate-owned. This repo now has real HTTP clients
  (`orchestrator/clients/http_movement.py`, `http_grip.py`) and proposed
  contracts (`contracts/movement_api.md`, `contracts/grip_api.md`) for them,
  but the endpoints themselves are not yet online — do not assume they are
  reachable.
- **YOLO detection tuning** for the specific disassembly-part vocabulary is
  still moving; the orchestrator runs against mocks for `next_part` in the
  interim (see [System: Orchestrator](./orchestrator.md)).
- **Two VLM roles from the task spec** — VLM next-part selection (an
  alternative `PerceptionClient.next_part` backend) and VLM grip
  verification (a second opinion alongside the binary grip sensor). Both
  have a clean seam in the Protocol design but neither is implemented — see
  [System: Orchestrator](./orchestrator.md) "Two future VLM roles".

## Test suite

105 pytest tests (`tests/`), up from 86 before the shared-token auth layer:
86 covering pure logic in perception/pose/damage (schemas, image/tensor
codecs, the LocateAnything token parser, prompt building, the damage bin
policy, FastAPI route wiring with model adapters mocked) plus the full
disassembly loop end-to-end against mocks (rectify-retry, reject-bin
routing, blacklisting an ungraspable part, bounded termination), plus 19 new
`test_auth.py` tests (7 in `tests/orchestrator/`, 4 each in
`tests/{damage,perception,pose}/`) covering the `require_token` dependency —
disabled when `WBK_API_TOKEN` unset, 401 on missing/wrong token, accepted
via header or `?token=` query param, `/health` always open — see
[ADR 0009](../Decisions/0009-shared-token-auth.md). No GPU, no model
weights, no `OPENROUTER_API_KEY`, no network, no hardware. See
[SOP: running the tests](../SOP/running_tests.md) for the conftest.py
per-stage import-root subtlety and what's intentionally NOT covered
(`*.load()`/`*.infer()`/`*.estimate()` on all five real model adapters). This
count is Python-only. `frontend/` has its own **Vitest** unit suite — 26
tests across 4 files (`npm test` → `vitest run`, jsdom env,
`frontend/vitest.config.ts`), covering `config/runtime.ts`'s endpoint
precedence resolution, `lib/stages.ts`'s state→stage mapping, the
event-reducer logic in `lib/derive.ts` (`tallyBins`, `deriveInspections`,
`deriveGrip`, `currentPart`), and the `apiToken` auth-header/query-param
wiring in `lib/api.ts` — see [System: Dashboard](./dashboard.md) for
detail. `npm run build` (`tsc -b && vite build`) remains the type-check +
production-bundle gate on top of that.

CI: `.github/workflows/tests.yml` has two jobs. `pytest` runs `uv sync
--frozen && uv run pytest -q` (105 tests). `frontend` runs `npm ci`, then
`npm test` (the 26-test Vitest suite), then `npm run build` — so unit tests,
type-check, and build all gate every push/PR to `main`. Green as of
`7cf5211` ("Add GitHub Actions CI to run tests on push/PR to main"),
extended to cover the frontend suite once Vitest landed, and again for the
shared-token auth tests.
