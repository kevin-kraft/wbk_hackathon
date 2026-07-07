# Robot Control — the Jetson movement bridge (`robot_control/`)

## Related Docs
- [Architecture](./architecture.md) — pipeline overview; this service fills the "Movement (arm)" row
- [System: Orchestrator](./orchestrator.md) — "Teammate-owned contracts" section, the `HttpMovement` client, `MOVEMENT_URL`
- [Integration Points & Wire Contracts](./integration_points.md) — the shared-token auth convention this service reuses
- [ADR 0009: shared-token auth](../Decisions/0009-shared-token-auth.md) — the auth pattern `robot_control/app/auth.py` matches
- [ADR 0010: robot_control integration](../Decisions/0010-robot-control-integration.md) — why/how it was containerized and wired in, and the open orchestrator-adapter gap
- `robot_control/README.md` (in-repo) — the module's own README (endpoint examples, calibration file layout); this doc adds the `.agent/` cross-reference layer, not a duplicate

## What it is

`robot_control/` is **Group 2's** Jetson-side FastAPI bridge to the physical
LARA5/NEURA robot arm. It is the repo's **movement** stage — it fills the
`MOVEMENT_URL` slot the orchestrator has held as a teammate-owned placeholder
since the orchestrator was added (see [System: Orchestrator](./orchestrator.md)
"Teammate-owned contracts"). It was merged in from an external
`robot_control` branch (commit `604733a`, "Merge robot_control service from
robot_control branch (Group 2)") — **only the `robot_control/` folder** was
taken from that branch, nothing else.

CPU-only. No ML stack, no GPU. It talks to the robot over a **raw TCP
socket**, not the richer HTTP APIs the rest of this repo's stages use.

## How it talks to the robot

`robot_control/app/robot_socket_client.py` (`robot_socket_client`, a module
singleton) opens a TCP connection to `ROBOT_HOST:ROBOT_PORT` (default
`127.0.0.1:65432` — the LARA5/NEURA robot socket server, normally running on
the same Jetson) and speaks a simple JSON request/response protocol: send
`{"function": <name>, "args": [...], "kwargs": {...}}`, read back the
result. Every router in this service is a thin FastAPI wrapper around calls
through that one client.

## Routers (`robot_control/app/routers/`)

| Router | Prefix | Endpoints | Purpose |
|---|---|---|---|
| `commands` | — | `POST /command` | Legacy compatibility endpoint (kept for existing frontend/simulation code per `robot_control/README.md`) |
| `robot_commands` | — | `POST /robot/execute/` | Forwards a named command through an **allow-list**: `READ_COMMANDS` (e.g. `get_tcp_pose`, `motion_status`, `get_errors` — read-only telemetry) vs. `MOTION_COMMANDS` (e.g. `move_linear`, `move_joint`, `gripper`, `grasp`, `stop` — anything that moves the arm). Only names in `READ_COMMANDS \| MOTION_COMMANDS` are accepted (403 otherwise); motion commands run `init_program` first (see `robot_control/app/routers/robot_commands.py`) |
| `robot_workflows` | `/robot` | `POST /raw`, `GET /probe`, `POST /calibration/points`, `POST /calibration/solve`, `GET /calibration`, `POST /hover/plan`, `POST /hover/execute` | Higher-level workflows — see "Hover planning" and "Calibration" below |
| `joint_states` | — | `WS /ws/joint_states` | Streaming joint-state telemetry over a WebSocket |

`GET /health` is defined directly in `robot_control/app/main.py` (not a
router) and always returns `{"status": "ok"}` with no auth.

### Raw passthrough (`POST /robot/raw`)

Forwards **any** robot-socket function name with positional/keyword args —
the "v1 freedom endpoint" per `robot_control/README.md`. Gated by
`ALLOW_RAW_ROBOT_COMMANDS` (env, default `true`); set `false` to disable in
production. No allow-list here, unlike `/robot/execute/` — this is
deliberately the escape hatch, not a policy-checked path.

### Hover planning (`/robot/hover/plan`, `/robot/hover/execute`)

Combines a **KIP pose API** result (`KIP_API_BASE`, default
`https://max-utils.com/KIP/api`; `KIP_PIPELINE`, default `gdrnpp`) with a
saved calibration to compute a hover target in the robot's base frame, then
gates the move behind several independently-checked safety gates
(`robot_control/app/services/hover_service.py`, lettered A–F in
`robot_control/README.md`):

| Gate | Checks |
|---|---|
| A | selected pose instance's confidence ≥ `MIN_CONFIDENCE` (default `0.5`) |
| B | world XY point falls inside `WORKSPACE_BOX` (hardcoded in `app/env.py`: `x∈[-0.25,1.07]`, `y∈[-0.12,0.72]`) |
| C | calibration residuals (RMS/max) below threshold and a `tool_down_rpy` exists |
| D | target inside the taught base workspace box (with `WORKSPACE_BASE_MARGIN_M` margin, default `0.05`) |
| F | target within `MAX_TCP_JUMP_M` (default `0.60`) of the current TCP pose |

`POST /robot/hover/plan` computes and returns all gate results **without
moving the robot** — useful for dry-checking a shot before committing.
`POST /robot/hover/execute` re-runs the same plan and **only moves if every
gate passes AND the caller passes `"confirmation": "yes"`** (an exact string
match, not just truthy) — see `robot_control/app/routers/robot_workflows.py`.
Execution then: (1) serializes motion behind a backend lock, (2) moves to a
safe intermediate Z, (3) moves linearly to the hover target, (4) returns the
final TCP pose. Speed/acceleration are hard-clamped by `SPEED_CAP_MS`
(default `0.05`) and `ACCEL_CAP` (default `0.05`) regardless of what the
caller requests.

### Calibration (`/robot/calibration/*`)

`robot_control/app/services/calibration.py` + `transform.py` solve a rigid
transform (Umeyama/Kabsch, `transform.umeyama_rigid`) from world-frame
points (`p_world`) to base-frame points (`q_base`) collected via
`POST /robot/calibration/points`, then `POST /robot/calibration/solve`
writes `base_world.json`. `CALIB_RMS_MAX_M` (default `0.005`) and
`CALIB_MAX_ERR_M` (default `0.010`) are the thresholds hover-planning Gate C
checks the saved solution against. Calibration artifacts persist under
`JETSON_DATA_DIR/calibration/` (default `./data/calibration/`):
`session.json` (raw collected points) and `base_world.json` (solved
transform). This is a **separate calibration** from the orchestrator's own
eye-to-hand `T_base_cam` (see
[ADR 0006](../Decisions/0006-eye-to-hand-static-calibration.md)) — this one
solves a world↔robot-base correspondence for the hover workflow, not
camera↔base.

## Config (`robot_control/app/env.py`)

All plain `os.getenv` reads, no pydantic settings object (unlike the other
four services' `Settings` dataclasses):

| Var | Default | Purpose |
|---|---|---|
| `ROBOT_HOST` / `ROBOT_PORT` | `127.0.0.1` / `65432` | robot socket server address |
| `SOCKET_TIMEOUT` | `2.0` | socket call timeout (s) |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` in code | uvicorn bind — **containerized default is `9000`**, set via the Dockerfile's `ENV API_PORT=9000` and CMD, to match `contracts/movement_api.md`'s `MOVEMENT_URL` (see [ADR 0010](../Decisions/0010-robot-control-integration.md)) |
| `JOINT_STREAM_DT` | `0.05` | WS joint-state push interval (s) |
| `JETSON_DATA_DIR` | `./data` | calibration file root |
| `KIP_API_BASE` / `KIP_PIPELINE` | `https://max-utils.com/KIP/api` / `gdrnpp` | KIP pose API used by hover planning |
| `KIP_POLL_INTERVAL_S` / `KIP_POLL_TIMEOUT_S` | `0.4` / `180.0` | polling the KIP pose job |
| `CALIB_RMS_MAX_M` / `CALIB_MAX_ERR_M` / `CALIB_MIN_POINTS` | `0.005` / `0.010` / `3` | calibration-solve acceptance thresholds |
| `MIN_CONFIDENCE` | `0.5` | hover Gate A |
| `HOVER_CLEARANCE_M` | `0.10` | default hover height above target |
| `MAX_TCP_JUMP_M` | `0.60` | hover Gate F |
| `SPEED_CAP_MS` / `ACCEL_CAP` | `0.05` / `0.05` | hard motion caps |
| `WORKSPACE_BASE_MARGIN_M` | `0.05` | hover Gate D margin |
| `ALLOW_RAW_ROBOT_COMMANDS` | `true` | enables/disables `POST /robot/raw` |
| `WBK_API_TOKEN` | unset | shared-token auth (see "Auth" below) |

`WORKSPACE_BOX` is **not** an env var — it's hardcoded in `app/env.py` as
`((-0.25, 1.07), (-0.12, 0.72))`.

## Auth (`robot_control/app/auth.py`)

Matches [ADR 0009](../Decisions/0009-shared-token-auth.md)'s pattern exactly
(same env var, same header-or-query-param transport, same
`secrets.compare_digest` check) — implemented as its own copy in
`robot_control/app/auth.py` rather than importing the other services'
`require_token`, consistent with how perception/pose/damage/orchestrator
each carry their own copy (no shared import root across the five deployable
packages). Applied via `dependencies=[Depends(require_token)]` on **every**
router in `main.py` (`commands`, `joint_states`, `robot_commands`,
`robot_workflows`); `/health` is defined outside the router list and stays
open. See [ADR 0010](../Decisions/0010-robot-control-integration.md) for why
this was added during integration (the merged branch had no auth of its
own).

## Deployment

- **Dockerfile** (`robot_control/Dockerfile`): `python:3.11-slim`, CPU-only,
  `uvicorn app.main:app --host 0.0.0.0 --port 9000`. Image name
  `wbk-robot-control` locally, `ghcr.io/kevin-kraft/wbk-robot-control` when
  published.
- **Dev**: `docker-compose.yml` (repo root) registers a `robot_control`
  service, port `9000:9000`, env passthrough for `ROBOT_HOST`, `ROBOT_PORT`,
  `KIP_API_BASE`, `ALLOW_RAW_ROBOT_COMMANDS`, `WBK_API_TOKEN`.
- **Standalone/production**: `deploy/robot-control/docker-compose.yml` +
  `.env.example` — pulls the published GHCR image, runs with
  `network_mode: host` (so the container reaches the robot socket server on
  the Jetson's own `127.0.0.1:65432` without port mapping). This one is
  meant to run **on the Jetson itself**, next to the robot socket server —
  unlike the orchestrator/damage/dashboard standalone deploys, which run
  wherever is convenient.
- **CI**: `.github/workflows/publish-images.yml`'s GHCR publish matrix has a
  `robot-control` entry (`context: robot_control`) alongside `orchestrator`,
  `damage`, `dashboard`.

## What is NOT yet wired

The orchestrator's `HttpMovement` client (`orchestrator/clients/http_movement.py`)
still speaks the **draft** `contracts/movement_api.md` shape
(`POST /move_to_pose`, `POST /move_named`, `POST /gripper`) — it does not
call any endpoint this service actually exposes. See
[ADR 0010](../Decisions/0010-robot-control-integration.md) "Open gap" for
the adapter work still needed and why it can't be guessed.
