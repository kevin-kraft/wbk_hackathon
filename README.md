# wbk_hackathon — VLM-Guided Robotic Disassembly

WBK Hackathon Group · 2026-07-07

[![tests](https://github.com/kevin-kraft/wbk_hackathon/actions/workflows/tests.yml/badge.svg)](https://github.com/kevin-kraft/wbk_hackathon/actions/workflows/tests.yml)

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
             ┌──────────────────────  ORCHESTRATOR  (state machine, :8000) ─────────────────────┐
             ▼                                                                                   │
 scene cam ─► PERCEPTION ─► 6DoF POSE ─► GRASP PLANNING ─► MOVEMENT ─► [grip sensor] ─► DAMAGE ─► bin
              (yolo/sam3/    (foundation   (naive/future)   (Jetson)    (0/1 rectify)   (OpenRouter
               locate)        pose/giga)                                                  VLM)   └─► loop
```

The **orchestrator** drives the loop, calling each stage through pluggable
clients — so it runs today against mocks for the pieces still in progress (YOLO,
the Jetson movement endpoint, the grip sensor).

| Stage | Dir | Services (port) | Hardware | Status |
|---|---|---|---|---|
| **Orchestrator** | `orchestrator/` | orchestrator `8000` | CPU | ✅ built (mock-driven) |
| **Perception** | `perception/` | yolo `8001`, sam3 `8002`, locateanything `8003` | GPU (1 container) | ✅ scaffolded |
| **6DoF pose** | `pose/` | foundationpose `8004`, gigapose `8005` | GPU (2 containers) | ✅ scaffolded |
| **Grasp planning** | `orchestrator/` | naive placeholder | CPU | 🟡 stand-in |
| **Movement (arm)** | — | Jetson endpoint (teammate) | — | 🔧 in progress · [contract](contracts/movement_api.md) |
| **Grip detection** | — | pressure sensor (teammate) | — | 🔧 in progress · [contract](contracts/grip_api.md) |
| **Damage inspection** | `damage/` | damage `8006` | CPU | ✅ scaffolded |

### Orchestrator (`orchestrator/`)
The disassembly state machine that ties every stage together: locate next part →
pose → grasp plan → move (Jetson) → **verify grip via the 0/1 sensor, rectifying
failed grabs** → remove → inspect → sort. It depends only on client *interfaces*,
so it runs end-to-end **today against mocks** for the in-progress pieces. Try it:

```bash
python -m orchestrator.dry_run   # full loop, all hardware mocked
```

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

## Future (from the task spec — noted, not yet built)

- **VLM next-part selection** — pick the next part to disassemble from a **part
  description or a prompt**; slots in as an alternative `PerceptionClient.next_part`
  backend (see `orchestrator/`).
- **VLM grip verification** — a visual check that the grip is correct, running
  **alongside** the binary pressure sensor (catches wrong-part / partial grips the
  0/1 signal can't distinguish).
- Real **grasp-planning** module (replacing the naive placeholder) and the
  **movement** + **grip-sensor** endpoints (teammates; contracts in `contracts/`).

## Repo layout

```
orchestrator/ disassembly state machine + stage clients (CPU coordinator)
perception/   YOLO + SAM3 + LocateAnything   (1 GPU container)
pose/         FoundationPose + GigaPose       (2 GPU containers)
damage/       OpenRouter VLM damage inspection (CPU)
contracts/    proposed Jetson-movement + grip-sensor APIs (hand-off to teammates)
docs/         architecture.md
docker-compose.yml
```

Per-stage detail: [`orchestrator/README.md`](orchestrator/README.md) ·
[`perception/README.md`](perception/README.md) · [`pose/README.md`](pose/README.md) ·
[`damage/README.md`](damage/README.md).

## Status

Hackathon build (2026-07-07). Perception, 6DoF pose, and damage-inspection stages
are scaffolded against real, current model APIs. Grasp-planning and movement
modules are specified as the hackathon progresses.
