# ADR 0014: Robot target selection (real | sim | both), sim as a mirrored digital twin

## Related Docs
- [System: Orchestrator](../System/orchestrator.md) — "Robot target selection" section: `factory.py:_build_robot`, config fields, the `SIM_WARN` event
- [System: Architecture](../System/architecture.md) — pipeline diagram / stage table entries for the simulator
- [System: Dashboard](../System/dashboard.md) — the Real/Sim/Both toggle, `SourceToggle`, `PartSelector`, `SceneView`
- `contracts/simulation_api.md` — the Isaac Sim command-bus surface `IsaacSimMovement` adapts to, and the named-pose teach-table gap
- `contracts/sim_scene_capture.md` — the (still-unimplemented) draft for sim RGB-D capture; **out of scope for this ADR**, which covers arm motion + grip only
- [ADR 0005: mock-first, interface-seam integration](./0005-mock-first-interface-seam-integration.md) — the Protocol-seam pattern this decision extends (a sim client is just another `MovementClient`)
- [ADR 0010: robot_control integration](./0010-robot-control-integration.md) — the real-arm side of `MovementClient`; that adapter gap is independent of and unaffected by this ADR
- [SOP: deploying perception to a remote GPU server](../SOP/deploy_perception_gpu_server.md) — `docker-compose.remote-gpu.yml` runs the Isaac Sim backend alongside this feature during a `kip-ws` outage

## Status

Implemented (working tree at capture time, 2026-07-08, not yet committed).

## Context

Group 2 (KIT `ki_robotik_cv_seminar`) built an Isaac Sim backend
(`simulation_backend`, port `8100`) that can execute robot actions
(`move_tcp`, `open_gripper`/`close_gripper`, …) against a simulated LARA5 in
a digital-twin scene. This repo's loop already drives the **real** arm
through `HttpMovement`/`HttpGrip` (see [ADR 0010](./0010-robot-control-integration.md)).
Three needs motivated wiring the sim in as an alternative/parallel backend:

1. **Demo/dev without hardware risk** — run the full disassembly loop against
   the sim only, with zero chance of a real motion command reaching the arm.
2. **Live digital-twin visualization** — while actually driving the real
   arm, mirror every command into the sim so an audience/operator can watch
   a synchronized 3D view of the disassembly alongside (or instead of) the
   physical camera feed.
3. **A sim fault must never break a real run.** If the loop is driving
   hardware, a hiccup in the sim (network blip, Isaac worker not running,
   IK failure) cannot be allowed to fail or block the step.

## Decision

Add `robot_target` (env `ROBOT_TARGET`, default `real`) to
`OrchestratorConfig`, resolved once per orchestrator build in
`orchestrator/factory.py:_build_robot()`, and overridable **per-run** via
`POST /run`/`GET /events/run`'s `?target=` query param (no service restart —
the dashboard can flip it live, see [System: Dashboard](../System/dashboard.md)).
Three values:

- **`real`** (default) — unchanged: `HttpMovement`/`HttpGrip` against
  `MOVEMENT_URL`/`GRIP_URL`.
- **`sim`** — `IsaacSimMovement` (`orchestrator/clients/sim_movement.py`)
  against `MOVEMENT_SIM_URL`, plus `SimGrip` (assume-grasp) unless
  `GRIP_SIM_URL` is set, in which case `HttpGrip` is used instead.
- **`both`** — `TeeMovement` (`orchestrator/clients/tee_movement.py`) wraps
  the real `HttpMovement` as the **primary** (authoritative — its exceptions
  propagate and fail the step, exactly as `real` mode would) and the sim
  `IsaacSimMovement` as a **mirror** (best-effort — dispatched concurrently
  via a `ThreadPoolExecutor` so mirroring adds no serial latency; a mirror
  exception is caught and reported as a `SIM_WARN` `LoopEvent`, never
  raised). Grip stays **real-only** in `both` — the real motor-current
  sensor remains the sole rectify/retry gate ([ADR 0007](./0007-grip-motor-current-sensing.md)),
  since the sim has no grip endpoint or force model to meaningfully mirror.

`IsaacSimMovement` exists as a dedicated adapter — not a second
`HttpMovement` instance pointed at a different URL — because the sim does
**not** speak the synchronous `contracts/movement_api.md` shape. It's an
async command bus: `POST /simulation/actions/execute` returns
`{id, status:"queued"}` immediately, and the caller polls
`GET /simulation/debug/commands/{id}` to a terminal status. The adapter
hides that behind the same `MovementClient` Protocol
(`move_to_pose`/`move_named`/`set_gripper`) so the loop and `TeeMovement`
are unaware of the difference — same mock-first Protocol-seam discipline as
[ADR 0005](./0005-mock-first-interface-seam-integration.md).

## Alternatives considered

1. **A second, fully separate orchestrator instance pointed at the sim.**
   Rejected — duplicates the entire loop/state-machine/Protocol-seam
   machinery for no real benefit; the existing `MovementClient` Protocol
   already generalizes to "any backend that implements it," so a sim client
   is just another implementation, not a reason to fork the orchestrator.
2. **Treat real and sim as equal peers (voting/consensus) in `both` mode.**
   Rejected on safety grounds — a stalled, crashed, or logically-wrong sim
   command must never gate or fail a step that is actually moving hardware.
   The primary/mirror asymmetry makes the trust relationship explicit in the
   code (`TeeMovement.primary` vs. `.mirrors`) instead of leaving it as an
   implicit convention an operator has to remember.
3. **Reuse `HttpMovement` unmodified for the sim, pointed at
   `MOVEMENT_SIM_URL`.** Assumed workable before the sim's actual API was
   inspected; rejected once `contracts/simulation_api.md` confirmed the
   async submit/poll shape — a synchronous POST client cannot drive it.
4. **Resolve named poses (`home`, `clearance`, `ok_bin`, `reject_bin`,
   `inspect_*`) the same way for sim and real.** Rejected — the sim has no
   named-pose concept at all; `IsaacSimMovement` carries its own teach table
   (`SIM_NAMED_POSES` / `SIM_NAMED_POSES_FILE`, overlaid onto built-in
   placeholder defaults) rather than trying to derive or share the real
   arm's named poses, since the sim's workspace geometry is an independently
   modeled (and not yet measured) scene.

## Consequences

- **No grip-fault coverage in pure `sim` mode.** `SimGrip.is_grasped()`
  always returns `True` (or is forced off via `SIM_GRIP_ALWAYS=0` for
  testing), so `_grasp_with_retry`'s rectify/retry path is only
  meaningfully exercised against the real sensor. `both` mode is unaffected
  — its grip signal is always the real one.
- **`sim`/`both` fail fast on missing config.** `_build_robot()` raises
  `ValueError` immediately if `MOVEMENT_SIM_URL` is unset for those targets
  — a misconfigured demo fails at orchestrator-build time, not on the first
  move mid-run.
- **The named-pose teach table is placeholder data today.** `sim_movement.py`'s
  `_DEFAULT_NAMED_POSES` and `deploy/sim_named_poses.example.json` are a
  rough top-down layout so a sim run won't crash on an unmapped name — they
  are **not** measured teach points. Replacing them (and confirming the
  "orchestrator's base frame ≡ the sim's IK root frame" assumption) is
  tracked as an open item in `contracts/simulation_api.md`, not solved here.
- **Scene capture is a separate, still-open problem.** This ADR covers arm
  motion + grip only. Feeding perception/pose from a rendered Isaac frame
  instead of the real Zivid is `contracts/sim_scene_capture.md`'s job — as
  of this ADR the sim backend's `GET_ZIVID_DATA` command is unimplemented,
  so `sim`/`both` runs still need the real Zivid (or `StaticSceneCamera`)
  for perception input; only the arm/gripper backend switches.
- **Verified together with the concurrently-developed plan-mode feature.**
  The full working tree (this ADR's changes plus the ERP/LLM planning head,
  see `Tasks/archive/llm_orchestrated_disassembly_plan.md`) passes
  `uv run pytest` (204 tests collected, including the 22 new
  `tests/orchestrator/test_robot_target.py` / `test_sim_movement.py` tests)
  and `npm run build` cleanly as of 2026-07-08.
