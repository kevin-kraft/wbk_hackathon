# Simulation target — Isaac Sim backend (KIT `ki_robotik_cv_seminar`)

How the orchestrator drives a **simulated** robot instead of / alongside the real
Jetson arm. Selected by `robot_target` (`real` | `sim` | `both`) — see
`orchestrator/factory.py:_build_robot`, `MOVEMENT_SIM_URL` / `GRIP_SIM_URL` in
`orchestrator/config.py`, and the dashboard's Real/Sim/Both toggle.

## Where the simulator lives

- Repo: `gitlab.kit.edu/kit/wbk/pro/lernfabrik/age/ki_robotik_cv_seminar`
  (Group 2). Cloned & running on the **on-prem GPU workstation** (host `age`,
  our `kip-ws`) at `/home/age/projects/ki_robotik_cv_seminar`, branch
  `RobotMovement`.
- `simulation_backend/` — a FastAPI service (`deploy/start_simulation_backend.sh`,
  **port 8100**, `--host 0.0.0.0`). Isaac Sim itself runs as a separate worker
  process (`app/isaac_bridge/bridge.py`) in Isaac's own `python.sh` env.
- Isaac Sim is up on the box; the **:8100 API is not always running** — start it
  with the deploy script (needs the Isaac worker/bridge alongside it).

## The shape that matters: an async command bus, NOT our clean movement contract

`contracts/movement_api.md` assumes a synchronous `/move_to_pose`, `/move_named`,
`/gripper` that block until the motion completes. The Isaac backend is different:

1. `POST /simulation/actions/execute` (or `/actions/execute/batch`) enqueues a
   command and returns a `SimulationCommand{ id, status: "queued" }` **immediately**.
2. The Isaac worker polls `POST /simulation/internal/commands/next`, runs the
   action in the sim, and reports back via `/commands/{id}/status` + `/result`.
3. The caller **polls** the command status to learn success/failure.

→ A plain HTTP client can't drive this. **`orchestrator/clients/sim_movement.py`
provides the adapter** (`IsaacSimMovement`) — it maps our primitives onto the
command bus and blocks by polling `GET /simulation/debug/commands/{id}` to a
terminal status. The factory wires it in for `robot_target=sim|both`; point
`MOVEMENT_SIM_URL` at the sim's `:8100`.

### Adapter mapping + knobs (`sim_movement.py`)

| orchestrator call | sim action | notes |
|---|---|---|
| `move_to_pose(4x4)` | `move_tcp` `{position, orientation_quat:[w,x,y,z], steps}` | rotation → quaternion (Shepperd); base ≡ robot-root frame, metres |
| `set_gripper(closed)` | `close_gripper` / `open_gripper` | sim has fixed open/closed, no `width`/force |
| `move_named(name)` | a configured entry from the **named-pose table** | the sim has no named poses (see below) |

Grip in sim: the sim exposes **no grip endpoint**, so `sim` mode uses `SimGrip`
(assume-grasp — the rectify/retry path is exercised against the real arm). Set
`GRIP_SIM_URL` if a sim grip endpoint is ever added. In `both` mode the **real**
grip sensor stays authoritative.

Env knobs: `SIM_MOVE_STEPS` (default 60), `SIM_POLL_INTERVAL_S` (0.2),
`SIM_CMD_TIMEOUT_S` (60), `SIM_GRIP_ALWAYS` (1).

### Named-pose table — needs teaching ⚠️

`home`, `clearance`, `ok_bin`, `reject_bin`, `inspect_0..N` have **no sim
equivalent**. The adapter resolves each via a table (env `SIM_NAMED_POSES` inline
JSON, or `SIM_NAMED_POSES_FILE`); entries are either
`{"type":"move_tcp","params":{"position":[...],"orientation_quat":[w,x,y,z]}}`
(the **confirmed default representation** — Cartesian TCP poses) or, per entry,
`{"type":"move_joint","params":{"joints":[j1..j6,gL,gR]}}` (8 DOF). The built-in
defaults are **placeholders** (a rough top-down workspace layout) so a run won't
crash — replace them with measured poses in
`deploy/sim_named_poses.example.json` → point `SIM_NAMED_POSES_FILE` at it.
Open item: the actual measured positions (and verifying base ≡ robot-root frame
once the `:8100` service is live).

## Robot arm control (implemented)

`POST /simulation/actions/execute` — body `RobotActionRequest`:

```jsonc
{ "type": "move_tcp", "params": { /* action-specific */ } }
```

Action `type`s the executor supports (`services/simulation/robot_executer.py`):
`move_tcp`, `move_joint`, `move_linear`, `move_circular`, `move_composite`,
`open_gripper`, `close_gripper`, `move_to_target`, `move_to_slot_object`, `wait`,
plus debug (`debug_camera`, `debug_camera_move_tcp`). Batch:
`POST /simulation/actions/execute/batch` → `{ "mode": "sequential", "actions": [ ... ] }`.

Discover exact param names/types live: `GET /simulation/debug/actions/palette`
(returns an `ActionPalette`). `move_tcp` uses NVIDIA Lula IK and currently moves
the **flange/mount frame**, not the true finger TCP (see `docs/move_tcp_summary.md`).

Mapping our loop → sim actions (for the adapter):
- `move_to_pose(4x4)` → `move_tcp` with position + quaternion from the matrix.
- `set_gripper(closed)` → `close_gripper` / `open_gripper`.
- `move_named("home"|"clearance"|"inspect_i"|"ok_bin"|"reject_bin")` → the sim has
  **no named poses**; these must be resolved to joint/TCP targets (open question
  for Group 2) or handled via `move_to_slot_object` for the bins.

## Scene assets

- `POST /simulation/assets/spawn` — `AssetSpawnRequest{ asset_id, name, position, rotation, scale }`.
- `POST /simulation/assets/spawn/tray-slot` — spawn into a tray `{col,row}`.
- Asset types currently registered: `anker`, `poltopf`.

## Modes

- Live mirror (sim visualises the real arm's joint stream):
  `POST /simulation/live-bridge/start` | `/stop`, `GET /simulation/live-bridge/status`.
- Test sim: `POST /simulation/test/start` | `/stop`, `GET /simulation/test/status`.
- `POST /simulation/shutdown`.

## Camera images — NOT available yet ⚠️

There is a `GET_ZIVID_DATA` command type intended to return simulated Zivid RGB-D,
but it is **unimplemented** (`isaac_bridge/bridge.py` raises
`RuntimeError("GET_ZIVID_DATA is not implemented.")`), and there is no HTTP route
that returns a rendered image. Group 3's `datapipeline/` (synthetic data) is still
a stub. So the simulator **cannot yet feed our SceneCamera / perception / pose**
(`contracts/scene_camera_api.md`) — the real Zivid on the Jetson stays the scene
source until sim capture lands. When it does, it plugs in behind `SCENE_CAMERA_URL`
the same way, no loop changes.

## Auth / CORS

The KIT backend has permissive CORS for `localhost:5173` and no shared-token gate
of its own. If we front it, keep our `WBK_API_TOKEN` on the adapter side.
