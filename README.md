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

## Vision: ERP-driven, LLM-orchestrated disassembly

On top of the fixed loop, the pipeline runs **plan-driven**: the operator selects
the product on the station in an **ERP system** (mocked as a per-product dataset,
[`orchestrator/data/erp_products.json`](orchestrator/data/erp_products.json)); an
**LLM reads the ERP data and generates the ordered disassembly plan** ("first take
off part A, then remove part B …"); the orchestrator executes the plan **step by
step**, querying perception + 6DoF pose for each step's specific part; and an LLM
can **synthesize the arm actions** for each step from the instruction + pose.

```
 ERP product pick ─► LLM plan ─► per step: locate part ─► pose ─► LLM action synthesis ─► grasp/remove/inspect/sort
 (operator, mock)   (ordered      (perception grounds     (6DoF)   (constrained vocabulary,
                     steps)        the plan's part)                  validated, scripted fallback)
```

Safety is structural, not prompt-deep: the action-synthesis LLM is a **selector,
never a generator** — it picks from a fixed action vocabulary
([`orchestrator/actions.py`](orchestrator/actions.py)) and references
pipeline-computed poses by name; it never emits coordinates. A deterministic
validator rejects anything outside the vocabulary before it reaches the robot,
falling back to the scripted grasp sequence. Plan generation is similarly fenced:
the LLM may only **order and describe** the ERP's part list, never invent parts.
(ADR 0011 in `.agent/Decisions/` has the full rationale.)

Try it: `POST /run?dry_run=true&product=gearbox-demo`; preview a plan with
`GET /plan?product=…`; list products with `GET /products` — or pick a product in
the dashboard's run controls and watch the plan checklist fill in live. Runs
without a `product` keep the original perception-driven loop.

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
| **Movement (arm)** | `robot_control/` | robot-control `9000` (Jetson) | LARA5 robot | ✅ integrated (Group 2) · [contract](contracts/movement_api.md) |
| **Grip detection** | — | pressure sensor (teammate) | — | 🔧 in progress · [contract](contracts/grip_api.md) |
| **Damage inspection** | `damage/` | damage `8006` | CPU | ✅ scaffolded |
| **Dashboard (UI)** | `frontend/` | dashboard `5173` | — | ✅ built (live SSE) |

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

### Dashboard (`frontend/`)
A **separate static app** (React + Vite + Tailwind) that is the operator console
and live demo UI — it is deliberately *not* fused with the orchestrator (which
must run headless). It streams the loop from the orchestrator's SSE endpoint
(`GET /events/run`) and renders the 7-stage pipeline with the live REGRASP retry,
scene/inspection cameras, grip telemetry, damage verdicts, and bin tallies.
**Every service endpoint is runtime-configurable** (`frontend/public/config.json`,
editable per-machine with no rebuild), so services can be spread across hosts.
Works today against mocks — see [`frontend/README.md`](frontend/README.md).

## Quick start

```bash
# Perception (needs NVIDIA Container Toolkit)
docker compose up --build perception

# 6DoF pose — build the two GPU base images first (see pose/README.md), then:
docker compose up --build foundationpose gigapose

# Damage inspection (CPU)
OPENROUTER_API_KEY=sk-or-... docker compose up --build damage

# Dashboard UI (static; edit frontend/public/config.json to point at your hosts)
docker compose up --build dashboard        # http://localhost:5173
```

Each service exposes `GET /health`, `GET /docs` (OpenAPI), and its `POST` route.
The orchestrator additionally streams the live loop over `GET /events/run` (SSE),
which the dashboard consumes.

## Deployment

The Quick start above runs everything on one machine. The **hackathon deployment is
split across four hosts** — CPU coordination stays local, GPU inference runs on a
shared server, and the robot/cameras live on lab hardware. Services find each other
over **SSH port-forwards** (private, encrypted, no public exposure), and every
endpoint is runtime-configurable in `frontend/public/config.json` /
`deploy-local/config.json`.

### Topology

| Host | Runs | Reach |
|---|---|---|
| **Local PC** | orchestrator `:8000`, damage `:8006`, dashboard `:5173` | native / `docker compose` |
| **GPU server** (8× RTX PRO 6000 Blackwell) | perception (`wbk-perception`: yolo→`:8001`, locate→`:8003`; `wbk-sam3`→`:8002`), pose (foundationpose `:8004`, gigapose `:8005`), **YOLO training** | direct SSH, no VPN |
| **On-prem box** (`kip-ws`) | Isaac Sim backend `:8100` (simulated arm + scene/Zivid render) | KIT VPN (netns) |
| **Jetson** | robot_control `:9000`, scene_camera `:9002` (LARA5 arm + Zivid) | KIT VPN (netns) |

The orchestrator dials **`localhost:1800x`** for every remote service; SSH forwards
map those onto the right host, so the orchestrator config never changes when
services move.

### 1. GPU server — perception + pose

Services run as containers bound to `127.0.0.1` on the server (namespaced ports
`6767–6772`, `8004/8005`). Open the tunnel from the local PC (the `Host gpu-server`
block in `~/.ssh/config` carries the forwards):

```bash
ssh -N gpu-server        # forwards 18001→6767(yolo) 18002→6768(sam3) 18003→6769(locate)
                         #          18004→8004(fpose) 18005→8005(gigapose) 6006→6772(tensorboard)
```

Then bring up the local stack pointed at the tunnels:

```bash
docker compose -f docker-compose.yml -f docker-compose.remote-gpu.yml up -d orchestrator dashboard damage
```

`docker-compose.remote-gpu.yml` sets `PERCEPTION_*_URL` / `POSE_URL` to
`localhost:18001-18005`. **Do not** also start the local `perception`/`pose`
services — the tunnels replace them.

> Base images must be **Blackwell-capable** (`*:blackwell`, PyTorch 2.8 / CUDA 12.8);
> the stock pre-Blackwell images won't run on the RTX PRO 6000 GPUs.

### 2. Training the detection / segmentation models

Custom **YOLOv26** detectors + segmenters are trained on the GPU server from
synthetic Isaac-Sim data. Full runbook in [`training/README.md`](training/README.md);
in short:

```bash
# on the server (venv at /mnt/vss-data/kip/venv/yolo; workspace on the 3.3TB net drive)
ssh gpu-server 'bash -s' < training/setup_server.sh          # one-time: venv + ultralytics
# convert Isaac renders → YOLO datasets (boxes from instance masks = dense labels)
python isaac_to_yolo.py --task detmask --src ~/output/robot_subset_train --out .../parts_detmask
python isaac_to_yolo.py --task seg     --src ~/output/robot_subset_train --out .../parts_seg
# train (crash-resumable supervisor, rolling last-5 + best.pt, TensorBoard at localhost:6006)
bash train_supervised.sh --data .../parts_detmask/data.yaml --model yolo26m.pt     --name parts_detmask_v1 --device 0 --epochs 81 --imgsz 1536 --batch 16 --amp false
bash train_supervised.sh --data .../parts_seg/data.yaml     --model yolo26m-seg.pt --name parts_seg_v1     --device 2 --epochs 57 --imgsz 1536 --batch 16 --amp false
```

Notes: `--amp false` is required (AMP triggers a CUDA illegal-access in validation on
the Blackwell/torch-2.12 stack); all caches are redirected onto `/mnt/vss-data`
(`source training/env.sh`) because the root disk is near-full.

### 3. Deploying trained weights to the perception service

The YOLO service loads `YOLO_WEIGHTS` at startup. To serve a trained model, stage the
weights on the server and recreate the perception container with a `/weights` mount:

```bash
ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_yolo_weights.sh'
```

This copies `runs/parts_detmask_v1/weights/best.pt` → `/mnt/vss-data/kip/weights/`,
then recreates `wbk-perception` with `-e YOLO_WEIGHTS=/weights/parts_detmask.pt -v
/mnt/vss-data/kip/weights:/weights`. Verify: `GET :6767/health` → `loaded:true`, and
`YOLO(weights).names` lists the 18 part classes. Reload the dashboard and detection
runs against the real parts.

### 4. Jetson (robot + cameras)

Reached over the KIT VPN (isolated network namespace). `ssh jetson` forwards
`9000` (robot_control), `9002` (scene_camera), `5005` (joint state). See
[`deploy/`](deploy/) for the Jetson-native service units and
[`robot_control/README.md`](robot_control/README.md).

### Simulation vs. real

`ROBOT_TARGET` selects the movement/camera backend: `real` (Jetson), `sim` (Isaac
backend on the box, `MOVEMENT_SIM_URL=localhost:8100`), or `both` (mirror). Scene
capture/preview for the Sim path is served by the Isaac backend
(`POST /simulation/scene/{capture,preview,inspection}` — see
[`contracts/sim_scene_capture.md`](contracts/sim_scene_capture.md)).

## Future (from the task spec — noted, not yet built)

- **VLM next-part selection** — pick the next part to disassemble from a **part
  description or a prompt**; slots in as an alternative `PerceptionClient.next_part`
  backend (see `orchestrator/`).
- **VLM grip verification** — a visual check that the grip is correct, running
  **alongside** the binary pressure sensor (catches wrong-part / partial grips the
  0/1 signal can't distinguish).
- Real **grasp-planning** module (replacing the naive placeholder) and the
  **grip-sensor** endpoint (teammate; contract in `contracts/`). The **movement**
  endpoint has landed as `robot_control/` (Group 2's Jetson bridge); its live API
  (`/robot/hover/*`, `/robot/raw`, …) is richer than the draft
  [`movement_api.md`](contracts/movement_api.md), so the orchestrator's
  `HttpMovement` client still needs adapting to it (frames + pose conventions TBD
  with the robot team).

## Repo layout

```
orchestrator/ disassembly state machine + stage clients + SSE stream (CPU coordinator)
perception/   YOLO + SAM3 + LocateAnything   (1 GPU container)
pose/         FoundationPose + GigaPose       (2 GPU containers)
damage/       OpenRouter VLM damage inspection (CPU)
robot_control/ Jetson-side movement bridge to the LARA5 robot (CPU, :9000)
frontend/     operator console + live demo dashboard (React/Vite static app)
training/     YOLOv26 detection/segmentation training on synthetic Isaac data (GPU server) — see training/README.md
deploy/       per-service standalone compose files for single-service deploys (GHCR) — see deploy/README.md
contracts/    proposed Jetson-movement + grip-sensor APIs (hand-off to teammates)
docs/         architecture.md
docker-compose.yml
```

Per-stage detail: [`orchestrator/README.md`](orchestrator/README.md) ·
[`perception/README.md`](perception/README.md) · [`pose/README.md`](pose/README.md) ·
[`damage/README.md`](damage/README.md) · [`robot_control/README.md`](robot_control/README.md) · [`frontend/README.md`](frontend/README.md).

## Status

Hackathon build (2026-07-07). Perception, 6DoF pose, and damage-inspection stages
are scaffolded against real, current model APIs. Grasp-planning and movement
modules are specified as the hackathon progresses.
