# wbk_hackathon — VLM-Guided Robotic Disassembly

WBK Hackathon Group · 2026-07-07

## Goal

A robot arm that **disassembles a part step by step**, guided by vision models in
the loop. The system does three things:

1. **Identify the next part to disassemble** — locate/point to the next component
   to remove, in the correct sequence.
2. **Rectify grabbing mistakes** — verify the grip after a pick attempt; if the
   grasp failed or grabbed the wrong component, detect it and retry / correct.
3. **Quality inspection (OK / not-OK)** — after removal, judge each part as OK or
   **damaged**, and sort it into a working bin or a separate reject bin.

## Architecture

Pipeline of containerized microservices (FastAPI, base64-in-JSON contracts). Full
detail in [`docs/architecture.md`](docs/architecture.md).

```
 scene cam ─► PERCEPTION ─► 6DoF POSE ─► GRASP PLANNING ─► MOVEMENT ─► DAMAGE ─► bin
              (yolo/sam3/    (foundation   (future)         (future)     (OpenRouter
               locate)        pose/giga)                                  VLM)   └─► loop
```

| Stage | Dir | Services (port) | Hardware | Status |
|---|---|---|---|---|
| **Perception** | `perception/` | yolo `8001`, sam3 `8002`, locateanything `8003` | GPU (1 container) | ✅ scaffolded |
| **6DoF pose** | `pose/` | foundationpose `8004`, gigapose `8005` | GPU (2 containers) | ✅ scaffolded |
| **Grasp planning** | — | — | — | ⏳ future |
| **Movement** | — | — | — | ⏳ future |
| **Damage inspection** | `damage/` | damage `8006` | CPU | ✅ scaffolded |

### Perception (`perception/`)
Three independent FastAPI apps in one CUDA container (supervisord):
- **yolo** — Ultralytics YOLO detection.
- **sam3** — Meta **SAM 3** (`facebook/sam3`, gated) promptable segmentation
  (point/box **and** text/concept prompts).
- **locateanything** — NVIDIA **LocateAnything-3B**, text query → boxes/points.

### 6DoF pose (`pose/`)
Two **alternative** estimators, each its own GPU container (their native stacks
conflict — can't co-locate). Mirrors the KIP `kip-pose-viewer` reference.
- **foundationpose** — RGB-D + CAD mesh → 6DoF pose.
- **gigapose** — RGB or RGB-D + CAD templates → 6DoF pose (+ score/stage).

Both return `T_cam_obj` (4x4, OpenCV camera frame, metres) via `POST /pose`.

### Damage inspection (`damage/`)
The arm holds a removed part to an inspection webcam; multi-angle shots go to
`POST /inspect`. A **VLM via OpenRouter** compares them against known-good /
known-damaged references and returns `{verdict, damaged, confidence, bin, …}`.
Only a clean `ok` → `ok_bin`; `damaged`/`uncertain` → `reject_bin`.

## Quick start

```bash
# Perception (needs NVIDIA Container Toolkit)
docker compose up --build perception

# 6DoF pose — build the two GPU base images first (see pose/README.md), then:
docker compose up --build foundationpose gigapose

# Damage inspection (CPU)
OPENROUTER_API_KEY=sk-or-... docker compose up --build damage
```

Each service exposes `GET /health`, `GET /docs` (OpenAPI), and its `POST` route.

## Repo layout

```
perception/   YOLO + SAM3 + LocateAnything   (1 GPU container)
pose/         FoundationPose + GigaPose       (2 GPU containers)
damage/       OpenRouter VLM damage inspection (CPU)
docs/         architecture.md
docker-compose.yml
```

Per-stage detail: [`perception/README.md`](perception/README.md) ·
[`pose/README.md`](pose/README.md) · [`damage/README.md`](damage/README.md).

## Tests

Fast, GPU/network-free unit tests for the pure logic across all three modules
(schemas, image codecs, the LocateAnything token parser, damage bin policy,
FastAPI route wiring with model adapters mocked). See [`tests/README.md`](tests/README.md).

```bash
uv sync            # installs the light test-only deps (pytest, pillow, numpy, ...)
uv run pytest      # whole suite
```

## Status

Hackathon build (2026-07-07). Perception, 6DoF pose, and damage-inspection stages
are scaffolded against real, current model APIs. Grasp-planning and movement
modules are specified as the hackathon progresses.
