# ADR 0010 — Integrating `robot_control/` (Group 2's Jetson bridge) as the movement stage

## Related Docs
- [System: Robot Control](../System/robot_control.md) — full service reference (routers, config, gates)
- [System: Orchestrator](../System/orchestrator.md) — "Teammate-owned contracts", `HttpMovement`, `MOVEMENT_URL`
- [Architecture](../System/architecture.md) — pipeline overview, the "Movement (arm)" row
- [ADR 0009: shared-token auth](./0009-shared-token-auth.md) — the auth pattern replicated here
- [ADR 0005: mock-first, interface-seam integration](./0005-mock-first-interface-seam-integration.md) — why the orchestrator could demo before this landed, and why the seam still isn't closed
- `contracts/movement_api.md` — the draft contract `HttpMovement` was written against; still not what this service exposes

## Context

The orchestrator has had a `MOVEMENT_URL` slot and a real `HttpMovement`
HTTP client (`orchestrator/clients/http_movement.py`) since it was added
(commit `3abc923`), written against a **draft** contract
(`contracts/movement_api.md`: `POST /move_to_pose`, `POST /move_named`,
`POST /gripper`) because the Jetson-side arm control wasn't built yet — see
[ADR 0005](./0005-mock-first-interface-seam-integration.md). A hardware
teammate later confirmed (2026-07-07, see `System/orchestrator.md`
"Teammate-owned contracts") that the real interface would be an
HTTP-adapter microservice wrapping NeuraPy, to be uploaded shortly.

That service arrived today as an external `robot_control` branch (Group 2's
work): a FastAPI bridge to the LARA5/NEURA robot socket server with
low-level command forwarding, KIP-pose-driven hover planning/execution, and
calibration. It was built independently, against its own frontend/demo
needs, not against `contracts/movement_api.md` — so integrating it meant
three separable problems: (1) get only the relevant code into this repo,
(2) make it buildable/deployable/consistent with this repo's conventions,
(3) reconcile its actual API shape with what the orchestrator expects.

## Decision

**1. Cherry-pick only the service folder.** `git merge`d the `robot_control`
branch (commit `604733a`) but kept **only `robot_control/`** — the branch
carried other, unrelated Jetson-project content that doesn't belong in this
repo. This mirrors how every other stage (`perception/`, `pose/`, `damage/`)
is a self-contained directory.

**2. Vendor `RobotCommand` instead of chasing the external import.** The
code imported `from shared.jetson import RobotCommand` — a module that
lives in the out-of-repo Jetson project root (the branch's original
context), not in this repo. Rather than trying to also pull in `shared/`
(more branch content, more coupling to a tree this repo doesn't own), a
minimal equivalent (`{function_name, args, kwargs}`) was vendored directly
into `robot_control/app/schemas.py` (commit `361fe9a`). Consequence: this
copy can drift from the external `shared.jetson` definition if that project
changes it independently — acceptable, since the shape is a 3-field passthrough
struct unlikely to change, and the alternative (importing an out-of-repo
package) would make this service **not** independently buildable, breaking
the "every stage is self-contained" convention every other service follows
(see [Integration Points](../System/integration_points.md), "Independently
containerizable").

**3. Port `9000`, not the code's own default of `8000`.** `robot_control/app/env.py`
defaults `API_PORT` to `8000` — but the orchestrator's `:8000` is already
taken (`orchestrator/config.py`'s `MOVEMENT_URL` default is
`http://jetson.local:9000`, and `contracts/movement_api.md` was drafted
against `:9000`). Rather than changing the orchestrator's contract or config
defaults, the Dockerfile pins the container to `9000` (`ENV API_PORT=9000`,
`EXPOSE 9000`, uvicorn `--port 9000`) — the code's own `8000` default is only
ever seen if someone runs `python -m app.main` directly outside the
container.

**4. Add shared-token auth, matching ADR 0009.** The merged branch had **no
auth of any kind** — every other service in this repo already gates its
work endpoints behind `WBK_API_TOKEN` (see
[ADR 0009](./0009-shared-token-auth.md)). Added `robot_control/app/auth.py`
as a fifth copy of the same `require_token` dependency (env token,
`Authorization: Bearer` or `?token=`, `secrets.compare_digest`), applied to
**every** router in `main.py` via `dependencies=[Depends(require_token)]`;
`/health` stays exempt, same convention as every other stage. This closes
what would otherwise have been the one unauthenticated work-endpoint gap in
the whole system.

**5. Register in both compose surfaces + CI.** Added to the root
`docker-compose.yml` (dev, alongside the other five services) and to a new
`deploy/robot-control/` (standalone GHCR-image compose + `.env.example`,
`network_mode: host` because it needs to reach the robot socket server on
the Jetson's own `127.0.0.1` — the only deploy target in `deploy/` that
needs host networking, since it's the only one meant to run **on** a
specific physical machine rather than "wherever is convenient"). Added a
`robot-control` entry to `.github/workflows/publish-images.yml`'s GHCR
publish matrix (context `robot_control`).

**Verification performed**: image builds standalone; the app boots with all
four routers mounted; `GET /health` returns 200 with no token required;
`WBK_API_TOKEN` set → 401 on missing/wrong token, 200 with the correct
token (header or query param).

## Open gap — the orchestrator↔movement adapter is NOT written

`robot_control` exposes a materially different, richer API
(`/robot/hover/plan`, `/robot/hover/execute`, `/robot/execute/`,
`/robot/raw`, `/robot/probe`, `/robot/calibration/*`, `WS /ws/joint_states`)
than the three flat endpoints `contracts/movement_api.md` drafted and
`orchestrator/clients/http_movement.py` calls
(`/move_to_pose`, `/move_named`, `/gripper`). **No code bridges these two
shapes yet** — `HttpMovement` today would 404 against this service.

This was deliberately **not** guessed at, for two reasons:

- **Pose-vector convention is unconfirmed.** The robot side represents
  poses as `[x, y, z, rx, ry, rz]` 6-vectors (see the `move_linear` example
  in `robot_control/README.md`: `target_pose: [[0.4, 0.2, 0.3, 3.14, 0.0,
  1.9], ...]`) with what looks like a fixed "tool down" orientation
  (`tool_down_rpy` ≈ `[3.1415, 0, 1.9]`, also used as a calibration input in
  `POST /robot/calibration/solve`) — not the 4x4 row-major matrices
  `HttpMovement.move_to_pose` sends today, and not obviously the same
  Euler/RPY convention (order, degrees vs. radians framing, intrinsic vs.
  extrinsic) the orchestrator's grasp chain produces (`base_T_grasp`, see
  [ADR 0006](./0006-eye-to-hand-static-calibration.md)).
- **This drives real robot motion.** Guessing a frame or rotation
  convention wrong here doesn't fail loudly like a schema mismatch would —
  it moves a physical arm to the wrong pose. This needs the robot team to
  confirm the exact convention, not an inference from two example vectors
  in a README.

**What the adapter work will need, once confirmed:**
1. A decision on which side adapts: either a new `HttpMovement` client
   variant that calls `robot_control`'s actual routes (likely `/robot/hover/execute`
   for placing/hovering and `/robot/execute/` with `move_linear`/`gripper`
   for the rest), or a translation shim in front of it.
2. Confirmed conversion from the orchestrator's `base_T_grasp` 4x4 (metres,
   see [ADR 0006](./0006-eye-to-hand-static-calibration.md)) to whatever
   `[x,y,z,rx,ry,rz]` convention `robot_control` expects, including the
   `tool_down_rpy` fixed-orientation assumption — is the arm's approach
   always "tool down", or does the orchestrator's own approach-axis
   reasoning (`grasp_approach_dist`, `NaiveTopDownGrasp._standoff`) need to
   carry through instead?
3. A decision on `move_named` (`home`, `clearance`, `inspect_0..N`,
   `ok_bin`, `reject_bin` — see `contracts/movement_api.md`): `robot_control`
   has no equivalent named-pose endpoint today; either it needs one, or the
   orchestrator's adapter resolves those names to raw poses/hover calls
   itself.
4. Whether `/gripper`'s "must block until settled/stalls" requirement
   (needed so the grip-current read right after is steady-state, not
   inrush — see [ADR 0007](./0007-grip-motor-current-sensing.md)) is
   satisfied by `robot_control`'s `gripper`/`grasp`/`release`
   `MOTION_COMMANDS`, or needs an explicit wait added in the adapter.

Until this lands, `robot_control` is **built, deployed, and reachable** but
**not yet in the orchestrator's real (non-dry-run) execution path** — the
Protocol seam (`MovementClient`, see [System: Orchestrator](../System/orchestrator.md))
means swapping in a working adapter needs no `loop.py` changes once written.

## Consequences

- `robot_control/` is a sixth deployable package with its own copy of
  `require_token` — six now, if the grip-sensor endpoint also lands as an
  in-repo service later (`perception`, `pose`, `damage`, `orchestrator`,
  `robot_control`, +grip).
- The vendored `RobotCommand` in `robot_control/app/schemas.py` is a
  duplicate definition to keep in sync manually if the external
  `shared.jetson.RobotCommand` it was copied from ever changes shape.
- Port `9000` for this container is now load-bearing across three places
  that must stay consistent: the Dockerfile's `ENV`/`EXPOSE`/`CMD`, the root
  `docker-compose.yml` port mapping, and `contracts/movement_api.md`'s
  documented `MOVEMENT_URL` default — a future change to any one needs the
  other two updated too.
- The pipeline's "Movement (arm)" stage is now **✅ integrated** at the
  service level (see root `README.md`'s status table, updated the same day)
  but **not yet live end-to-end** — real (non-dry-run) orchestrator runs
  still cannot move the arm until the adapter gap above is closed.
