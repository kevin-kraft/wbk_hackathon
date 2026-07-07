# Architecture — VLM-Guided Robotic Disassembly

## Related Docs
- [Integration Points & Wire Contracts](./integration_points.md) — the base64-in-JSON contracts, model-adapter pattern, HF cache mount
- [ADR: perception shared container vs. pose split containers](../Decisions/0001-perception-shared-container-pose-split-containers.md)
- [ADR: perception model stack](../Decisions/0002-perception-model-stack.md)
- [ADR: damage fail-safe sort policy](../Decisions/0003-damage-failsafe-sort-policy.md)
- [ADR: pose contract reuses kip-pose-viewer](../Decisions/0004-pose-contract-reuses-kip-pose-viewer.md)
- [SOP: running the services](../SOP/running_services.md)
- [SOP: running the tests](../SOP/running_tests.md)

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
scene cam ─► PERCEPTION ─► 6DoF POSE ─► GRASP PLANNING ─► MOVEMENT ─► DAMAGE ─► bin
             (yolo/sam3/    (foundation   (future)         (future)     (OpenRouter
              locate)        pose/giga)                                  VLM)   └─► loop back to PERCEPTION
```

| Stage | Dir | Services (port) | Containers | Hardware | Status |
|---|---|---|---|---|---|
| Perception | `perception/` | yolo `:8001`, sam3 `:8002`, locateanything `:8003` | 1 (supervisord) | GPU | Built |
| 6DoF pose | `pose/` | foundationpose `:8004`, gigapose `:8005` | 2 (siblings) | GPU | Built |
| Grasp planning | — | — | — | — | Future — not built |
| Movement | — | — | — | — | Future — not built |
| Damage inspection | `damage/` | damage `:8006` | 1 | CPU | Built |

Grasp planning and movement are the two stages between pose and damage that do
not exist yet in this repo — no directories, no code. Confirmed by `find` scan
of the repo root: only `perception/`, `pose/`, `damage/`, `docs/`, `tests/` exist.

All stages are wired together in [`docker-compose.yml`](../../docker-compose.yml)
at the repo root (one `services:` entry per container: `perception`,
`foundationpose`, `gigapose`, `damage`).

## Stage 1 — Perception (`perception/`)

Three **independent FastAPI apps in one CUDA container**, run as separate
processes under `supervisord` (see [`perception/supervisord.conf`](../../perception/supervisord.conf)).
Each is its own `uvicorn` process on its own port — this is a deliberate
choice so any one service can be lifted into its own container later without
a rewrite (see ADR 0001).

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

**Grasp planning** and **movement** are the two pipeline stages between pose
and damage. As of this scan (2026-07-07) there is no code, directory, or
service for either — they are named only in the README/architecture diagrams
as future work. Do not assume any contract for them exists yet.

## Test suite

81 pytest tests (`tests/`) covering pure logic only — schemas, image/tensor
codecs, the LocateAnything token parser, prompt building, the damage bin
policy, and FastAPI route wiring with model adapters mocked. No GPU, no model
weights, no `OPENROUTER_API_KEY`, no network. See
[SOP: running the tests](../SOP/running_tests.md) for the conftest.py
per-stage import-root subtlety and what's intentionally NOT covered
(`*.load()`/`*.infer()`/`*.estimate()` on all five real model adapters).

CI: `.github/workflows/tests.yml` runs `uv sync --frozen && uv run pytest -q`
on push/PR to `main`. Currently green (last commit: `7cf5211`, "Add GitHub
Actions CI to run tests on push/PR to main").
