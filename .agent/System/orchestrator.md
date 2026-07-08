# Orchestrator — the disassembly state machine

## Related Docs
- [Architecture](./architecture.md) — full pipeline overview, per-stage service map
- [Integration Points & Wire Contracts](./integration_points.md) — perception/pose/damage wire contracts the orchestrator's HTTP clients speak, plus the `/events/run` SSE contract
- [System: Dashboard](./dashboard.md) — the frontend app that consumes `/events/run`
- [ADR: mock-first, interface-seam integration](../Decisions/0005-mock-first-interface-seam-integration.md) — why the loop was built against Protocols + mocks before teammate-owned hardware existed
- [ADR: eye-to-hand static calibration + grasp chain composition](../Decisions/0006-eye-to-hand-static-calibration.md) — why `T_base_cam` is a single static matrix and how the grasp chain composes
- [ADR: motor-current-based grip sensing](../Decisions/0007-grip-motor-current-sensing.md) — why `/grip` moved from a binary pad to analog current, and the end-stop pitfall
- [ADR: dashboard is a separate static app](../Decisions/0008-frontend-separate-static-app.md) — why the SSE endpoint below exists and why CORS is on
- [ADR: shared-token auth](../Decisions/0009-shared-token-auth.md) — why `/run`/`/events/run` are gated and why the orchestrator also attaches the token downstream
- [System: Robot Control](./robot_control.md) — the movement service that landed, and its actual (different) API
- [ADR: robot_control integration](../Decisions/0010-robot-control-integration.md) — why `HttpMovement` still can't drive it yet
- [ADR: LLM action selector, constrained vocabulary](../Decisions/0011-llm-action-selector-constrained-vocabulary.md) — why the action-synthesis LLM can only select, never author, arm poses
- [ADR: robot target selection (real \| sim \| both)](../Decisions/0014-robot-target-real-sim-both.md) — why sim is a mirrored digital twin, not a peer, and why `IsaacSimMovement` is a dedicated adapter
- `contracts/simulation_api.md` — the Isaac Sim command-bus surface `IsaacSimMovement` speaks, and the named-pose teach-table gap
- [Tasks/archive: ERP-driven, LLM-orchestrated disassembly plan (PRD)](../Tasks/archive/llm_orchestrated_disassembly_plan.md) — the shipped vision this doc's "Plan mode" section reflects
- [SOP: running the orchestrator dry-run](../SOP/running_orchestrator_dry_run.md)
- [SOP: running the services](../SOP/running_services.md)
- `orchestrator/README.md` (in-repo) — the module's own README; this doc adds the `.agent/` cross-reference layer on top, not a duplicate

## What it is

`orchestrator/` (added commit `3abc923`) is the **connective tissue** that runs
the whole disassembly loop end-to-end, one part at a time, by calling every
pipeline stage through a small client interface. It is the only piece of the
repo that knows the full sequence; every other directory (`perception/`,
`pose/`, `damage/`) is a single stage that doesn't know about its neighbors.

It ships as its own container (`orchestrator` service in
[`docker-compose.yml`](../../docker-compose.yml), port `:8000`, CPU-only —
it's a coordinator, not a model host).

## Two loop modes, one shared per-part machinery (`orchestrator/loop.py`)

`DisassemblyOrchestrator.run(product: str | None = None)` dispatches on
whether a `product` is given: no `product` runs `_run_fixed()` (the original
pipeline, event-for-event unchanged); a `product` (requires a `PlanProvider`
wired) runs `_run_planned(product)` (added 2026-07-08, see "Plan mode"
below). Both share `_process_part()` for the per-part sequence:

```
POSE     pose.estimate(frame, part)          — 6DoF T_cam_obj
PLAN     grasp.plan(pose, part)              — grasp pose in base frame
GRASP    _grasp_with_retry(...):
           _grasp_actions(...) → scripted (pre_grasp, grasp, gripper-close)
                                  or, if an ActionSynthesizer is wired,
                                  LLM-proposed + validated (see "Plan mode")
           execute_actions(...)
           grip.is_grasped()  ── sensor=0 ──► grasp.replan(...); retry
                               (up to config.max_grasp_attempts, default 3)
           sensor=1 ──► confirmed, continue
           (the boolean itself is derived from gripper motor current on
           the hardware side, not a binary pad — see "Teammate-owned
           contracts" below; the `GripSensor` Protocol and loop logic are
           unaffected)
REMOVE   move.move_named("clearance")        — lift clear
         perception.is_present(after, part)  — confirm it's actually gone
           still present => wrong/failed grab: release, retry from LOCATE
INSPECT  present to inspection_camera for config.inspection_angles angles
         damage.inspect(images, part)        — OK/damaged verdict
SORT     move.move_named(inspection.bin); drop; move.move_named("home")
```

**Fixed mode** (`_run_fixed()`) loops `LOCATE   perception.next_part(frame)`
— next part to remove, `None` => done — into `_process_part()`, repeating
until `next_part()` returns `None` or a part is blacklisted. Unchanged from
before plan mode existed.

**"Rectify grabbing mistakes"** (one of the three product jobs — see
[Architecture](./architecture.md)) lives entirely in `_grasp_with_retry`: the
grip sensor gates progress and a failed read (`sensor=0`) triggers a
re-planned retry, not just a repeat of the same grasp. A part that never
confirms a grasp after `max_grasp_attempts` gets **blacklisted** in fixed
mode (`blacklist: set[str]`) or **blocks the run** in plan mode (see below)
so a single ungraspable part can't spin the loop forever.

Every step emits a `LoopEvent` (`step`, `state`, `message`, `data`). Fixed-mode
states: `LOCATE`, `POSE`, `GRIP`, `REGRASP`, `SKIP`, `REMOVE`, `RECHECK`,
`INSPECT` (implicit via `SORT`), `SORT`, `BLOCKED`, `DONE`, `SUMMARY`. Plan
mode adds `PLAN_GENERATED`, `STEP`, and `GUARDRAIL` (see below). These drive
both the demo narration (`dry_run.py` prints them) and the FastAPI response
(`app.py` collects them into `events: list[dict]`, or streams them over SSE).

## Plan mode (`_run_planned`, added 2026-07-08 — ERP + LLM planning head)

`run(product="gearbox-demo")` (requires a `PlanProvider` wired, else
`ValueError`) replaces "perception decides what's next" with "a generated,
ordered plan decides what's next"; perception's role shifts from **sequencer**
to **grounder/verifier**. Implements the vision captured in
[Tasks/archive: ERP-driven, LLM-orchestrated disassembly plan](../Tasks/archive/llm_orchestrated_disassembly_plan.md)
(now shipped; kept for provenance).

```
PLAN_GENERATED  plan_provider.get_plan(product)         — once, at the start
                  emits the full plan (steps: [{part, action}], source, rationale)
for each plan step, in ERP/plan order:
  STEP     "plan step i/N: <action>"                    — narrate before locating
  LOCATE   perception.locate(frame, plan_step.part)      — ground the NAMED part
             not found  => SKIP this step, continue to the next (already
                            removed, or never present — no motion attempted)
  _process_part(...)                                     — same POSE→SORT as fixed mode,
                                                            with plan_step threaded through
                                                            for action-synthesis context
             outcome "removed" => advance to the next plan step
             outcome "retry"   => same plan step again (bounded by max_steps globally,
                                   not a separate per-step counter)
             outcome "skipped" => BLOCKED, loop stops — ordered disassembly means a
                                   part later in the plan may be physically under
                                   the one that couldn't be grasped
DONE / SUMMARY  when every plan step is consumed (or the loop stops early)
```

Retries of the same plan step are bounded by the loop's single global `step`
counter against `config.max_steps` — there is no separate per-step retry
budget; `max_grasp_attempts` (inside `_grasp_with_retry`) still bounds
grasp-level retries within one step attempt as before.

### Planning head — turning a product into a `Plan` (`clients/erp.py`, `clients/llm_planner.py`)

- **ERP data** for the hackathon is a per-product JSON dataset,
  `orchestrator/data/erp_products.json` (ships in the image; override via
  `ERP_PRODUCTS_PATH`): `{"products": {"<id>": {"name", "description",
  "parts": [{"part", "action", "notes"}]}}}`. Two products ship today:
  `gearbox-demo` (cover → bracket → gear) and `valve-block` (solenoid →
  fitting_left → fitting_right).
- **`StaticPlanProvider`** (`clients/erp.py`) — stdlib only, no LLM: turns an
  entry into a `Plan` in the listed (ERP) order, `source="static"`.
- **`LlmPlanProvider`** (`clients/llm_planner.py`) — asks an LLM (via
  `clients/openrouter.py`, see below) to re-order and describe the same
  parts. **Guardrail**: the LLM may only ORDER and DESCRIBE — the returned
  `steps` must be an exact permutation of the ERP part list (`sorted(parts)
  == sorted(known)`), else `RuntimeError`. Any exception (bad permutation,
  network error, malformed JSON) is caught in `get_plan()` and falls back to
  `build_static_plan(..., source="static-fallback")` — plan generation can
  never invent a part or block a run.
- **`PLANNER_MODE`** (env, default `auto`): `auto` — `LlmPlanProvider` if
  `OPENROUTER_API_KEY` is set, else `StaticPlanProvider`; `llm` — LLM
  required, error at `build_orchestrator()` time without a key; `static` —
  always the ERP order. Selected in `factory.py`'s `_build_plan_provider()`.
- Both providers satisfy the same `PlanProvider` Protocol
  (`clients/base.py`: `get_plan(product_id) -> Plan`, raises `ValueError` for
  an unknown product) — a real ERP client drops in with no loop changes,
  the same mock-first play as [ADR 0005](../Decisions/0005-mock-first-interface-seam-integration.md).

### Constrained action vocabulary — the runtime command-synthesis LLM (`actions.py`, `clients/llm_actions.py`)

**The safety-critical decision from the PRD, now resolved — see
[ADR 0011](../Decisions/0011-llm-action-selector-constrained-vocabulary.md)
for the full rationale and rejected alternatives.** Summary: the LLM is an
action **selector**, never a command **generator**. It picks from a fixed
vocabulary (`orchestrator/actions.py`) —

- `move_to_pose` referencing a pipeline-computed `pose_ref` (`pre_grasp` |
  `grasp` only) — the LLM never sees or emits coordinates; the matrices come
  from the `Grasp` object at execution time.
- `move_named` restricted, in the grasp context, to `home` | `clearance`
  only (a strict subset of the full named-pose universe).
- `gripper` open/close with an optional bounded `width` (`0 < width <=
  0.20` m).

— at most 8 actions, and a grasp sequence must end with exactly one
`gripper closed=true`. `validate_actions()` deterministically rejects ANY
violation (unknown kind/field, out-of-context named pose, wrong `pose_ref`,
missing/extra terminal gripper-close) **before** a `MovementClient` is
touched. On rejection (or any synthesis exception), `loop.py`'s
`_grasp_actions()` falls back to `scripted_grasp_sequence()` — identical
motion to the pre-plan-mode loop — and emits a `GUARDRAIL` `LoopEvent` so the
fallback is visible in the narration/dashboard, not silent.
`robot_control/`'s server-side workspace/velocity gates
([System: Robot Control](./robot_control.md)) remain the independent second
safety layer underneath this one.

LLM synthesis is **opt-in**: `ACTION_SYNTHESIS=llm` (default `"scripted"` —
no LLM anywhere in the motion path). `clients/llm_actions.py`'s
`LlmActionSynthesizer` implements `ActionSynthesizer`
(`synthesize(part, grasp, step) -> list[ArmAction]`); its prompt's entire
command surface is `actions.VOCABULARY_DOC` — a literal constant also used
by the validator, so the two can't independently drift in what they each
think is allowed.

### `clients/openrouter.py` — the shared LLM provider

Both `LlmPlanProvider` and `LlmActionSynthesizer` call
`clients/openrouter.py`'s `chat_json(config, messages)` — a minimal
OpenRouter `/chat/completions` wrapper (temperature 0, JSON response
format, `_extract_json()` strips markdown code fences if the model wraps its
JSON). This **mirrors `damage/client.py`'s pattern deliberately** (same
provider, same env-var family: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`;
new `PLANNER_MODEL`, default `anthropic/claude-sonnet-5`, covers both plan
generation and action synthesis) rather than adding a second LLM provider —
resolves PRD open question 1. Kept local to `orchestrator/` (not imported
from `damage/`) to match the repo's copy-per-service convention (same
reasoning as each service's own `auth.py`, see ADR 0009/0010).

## The Protocol seam (`orchestrator/clients/base.py`)

The orchestrator depends **only on Protocol interfaces**, never on concrete
implementations:

| Protocol | Real client | Talks to |
|---|---|---|
| `SceneCamera` | `StaticSceneCamera` (`clients/cameras.py`) | file/RGB-D source (RealSense TODO) |
| `PerceptionClient` | `HttpPerception` (`clients/http_perception.py`) | yolo `:8001` / sam3 `:8002` / locateanything `:8003` — now also `locate(frame, class_name)` for plan-mode grounding |
| `PlanProvider` | `StaticPlanProvider` / `LlmPlanProvider` (`clients/erp.py` / `clients/llm_planner.py`) | mock-ERP JSON, optionally an LLM (OpenRouter) — see "Plan mode" |
| `ActionSynthesizer` | `LlmActionSynthesizer` (`clients/llm_actions.py`), or `None` (scripted default) | OpenRouter, constrained to `actions.py`'s vocabulary — see "Plan mode" |
| `PoseClient` | `HttpPose` (`clients/http_pose.py`) | foundationpose `:8004` (configurable) |
| `GraspPlanner` | `NaiveTopDownGrasp` (`clients/naive_grasp.py`) | local, no network — placeholder only |
| `MovementClient` | `HttpMovement` (real, default) / `IsaacSimMovement` (sim) / `TeeMovement` (both — real primary + sim mirror) | **Jetson arm endpoint** (teammate-owned, external) and/or the Isaac Sim command bus — see "Robot target selection" below |
| `GripSensor` | `HttpGrip` (real, default) / `SimGrip` (sim, assume-grasp) / `HttpGrip` again in `both` (real stays authoritative) | **binary→motor-current sensor** (teammate-owned, external) — see [ADR 0007](../Decisions/0007-grip-motor-current-sensing.md) |
| `InspectionCamera` | `OpenCVInspectionCamera` (`clients/cameras.py`) | inspection webcam |
| `DamageClient` | `HttpDamage` (`clients/http_damage.py`) | damage service `:8006` |

Every Protocol also has a mock in `orchestrator/mocks.py` (`MockSceneCamera`,
`MockPerception` — now with `locate()` too, `MockPose`, `MockGraspPlanner`,
`MockMovement`, `MockGrip`, `MockInspectionCamera`, `MockDamage`,
`MockPlanProvider`, `MockActionSynthesizer`) — parameterized so tests and the
dry-run can drive specific scenarios (e.g. `MockGrip(fail_first=True)` to
exercise the rectify-retry path, `MockDamage(damaged_classes={"gear"})` to
exercise the reject bin, `MockActionSynthesizer(bad=True)` to exercise the
`GUARDRAIL` fallback). `factory.py`'s `dry_run=True` path wires
`MockPlanProvider`/`MockActionSynthesizer` too, so a plan-driven dry run
exercises the full validate→execute guardrail path with no ERP file or LLM.
`plan_provider`/`synthesizer` are both optional constructor args on
`DisassemblyOrchestrator` — `None` means fixed-mode-only (`synthesizer=None`
is also the scripted-only default even in plan mode).

`orchestrator/factory.py`'s `build_orchestrator(dry_run: bool)` is the single
switch point: `dry_run=True` wires every mock; `dry_run=False` lazily imports
and wires the real HTTP/OpenCV clients (lazy so `httpx`/`cv2`/`numpy` are
never required for the dry-run or the test suite). This Protocol-seam design
*is* the integration strategy — see
[ADR 0005](../Decisions/0005-mock-first-interface-seam-integration.md) for
why it was chosen and what it's meant to buy.

## Config (`orchestrator/config.py`)

Env-driven `OrchestratorConfig` dataclass: URLs for the repo's own stages
(`PERCEPTION_YOLO_URL`, `PERCEPTION_SAM3_URL`, `PERCEPTION_LOCATE_URL`,
`POSE_URL`, `DAMAGE_URL`) plus the two teammate-owned endpoints
(`MOVEMENT_URL` default `http://jetson.local:9000`, `GRIP_URL` default
`http://jetson.local:9001`); the simulator endpoints (`MOVEMENT_SIM_URL`,
`GRIP_SIM_URL`, both default empty) and `ROBOT_TARGET` (default `real`) that
select which of them the loop drives — see "Robot target selection" below;
behavior knobs `MAX_GRASP_ATTEMPTS` (default 3),
`MAX_STEPS` (default 50, the runaway-loop bound — also the global bound on
plan-step retries in plan mode), `INSPECTION_ANGLES` (default 3);
`api_token` (env `WBK_API_TOKEN`, default empty = auth disabled — see
"Auth" below); three hand-eye-calibration / grasp-geometry fields —
`T_base_cam`, `obj_T_grasp`, `grasp_approach_dist` — described next; and the
**planning head** fields (added 2026-07-08, see "Plan mode" above):

| Field | Env | Default | Meaning |
|---|---|---|---|
| `erp_products_path` | `ERP_PRODUCTS_PATH` | packaged `orchestrator/data/erp_products.json` | the mock-ERP dataset |
| `planner_mode` | `PLANNER_MODE` | `auto` | `auto` \| `llm` \| `static` — how plans are generated |
| `action_synthesis` | `ACTION_SYNTHESIS` | `scripted` | `scripted` \| `llm` — whether grasp motion is LLM-proposed |
| `openrouter_api_key` | `OPENROUTER_API_KEY` | `""` | same family `damage/` already uses |
| `planner_model` | `PLANNER_MODEL` | `anthropic/claude-sonnet-5` | covers both plan generation and action synthesis |
| `openrouter_base_url` | `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | — |

## Robot target selection (real | sim | both) — `factory.py:_build_robot`

Added 2026-07-08 (working tree at capture time, not yet committed) alongside
Group 2's Isaac Sim digital-twin backend landing (`ki_robotik_cv_seminar/
simulation_backend`, port `8100`). `config.robot_target` (env `ROBOT_TARGET`,
default `real`) picks which backend(s) the `MovementClient`/`GripSensor`
Protocol slots resolve to, in `factory.py:_build_robot()`:

- **`real`** — unchanged: `HttpMovement(config, config.movement_url)` +
  `HttpGrip(config, config.grip_url)`, the Jetson arm.
- **`sim`** — `IsaacSimMovement` (`clients/sim_movement.py`) against
  `MOVEMENT_SIM_URL`, plus `SimGrip` (assume-grasp; the sim exposes no grip
  endpoint) unless `GRIP_SIM_URL` is set, in which case `HttpGrip` is used
  against it instead. Raises `ValueError` at build time if
  `MOVEMENT_SIM_URL` is unset — fails fast, not on the first move.
- **`both`** — `TeeMovement` (`clients/tee_movement.py`) wraps the real
  `HttpMovement` as **primary** (authoritative — its errors fail the step)
  and the sim `IsaacSimMovement` as a **mirror**, dispatched concurrently via
  a `ThreadPoolExecutor` so mirroring adds no serial latency. A mirror
  exception is caught and turned into a `SIM_WARN` `LoopEvent`
  (`step=0, message="simulator {kind} error (ignored): {exc}"`) — it is
  **never raised**, so a sim hiccup can't break a run that is actually
  driving hardware. Grip stays real-only in `both` (`HttpGrip` against
  `grip_url`) — the real motor-current sensor remains the sole rectify/retry
  gate.

Overridable **per-run**, no restart: `POST /run?target=<real|sim|both>` and
`GET /events/run?target=<real|sim|both>` (`orchestrator/app.py`'s
`_config_for()`) construct a fresh `OrchestratorConfig` with `robot_target`
patched before calling `build_orchestrator()`. The dashboard's Real/Sim/Both
toggle (see [System: Dashboard](./dashboard.md)) uses this — the response
`target` field and the SSE `start` frame's `target` field report which
target the server actually used (see `RunStreamState.activeTarget` in the
frontend), in case `ROBOT_TARGET` was forced server-side.

**Why `IsaacSimMovement` is a dedicated adapter, not another `HttpMovement`:**
the sim does not speak the synchronous `contracts/movement_api.md` shape —
it's an async command bus (`POST /simulation/actions/execute` returns
`{id, status:"queued"}` immediately; the caller polls
`GET /simulation/debug/commands/{id}` to a terminal status). The adapter
maps our three primitives onto it and hides the polling:

| orchestrator call | sim action | notes |
|---|---|---|
| `move_to_pose(4x4)` | `move_tcp {position, orientation_quat:[w,x,y,z], steps}` | rotation → quaternion via Shepperd's method; base frame ≡ sim IK root frame (assumed); metres |
| `move_named(name)` | a configured entry from the **named-pose table** | the sim has no named poses — see below |
| `set_gripper(closed)` | `close_gripper` / `open_gripper` | sim has fixed open/closed, no `width`/force model |

The **named-pose table** (`home`, `clearance`, `ok_bin`, `reject_bin`,
`inspect_0..N`) is env-configurable (`SIM_NAMED_POSES` inline JSON, or
`SIM_NAMED_POSES_FILE` — see `deploy/sim_named_poses.example.json` /
`deploy/sim_named_poses.json`), overlaid onto built-in placeholder defaults
(a rough top-down layout) so an unmapped name doesn't crash a run. **The
built-in and shipped defaults are not measured teach points** — replacing
them with real positions is an open item (see `contracts/simulation_api.md`).
Env knobs: `SIM_MOVE_STEPS` (60), `SIM_POLL_INTERVAL_S` (0.2),
`SIM_CMD_TIMEOUT_S` (60), `SIM_GRIP_ALWAYS` (1, for `SimGrip`).

See [ADR 0014](../Decisions/0014-robot-target-real-sim-both.md) for the full
rationale and rejected alternatives (a second orchestrator instance, a
real/sim voting scheme). Note this is **arm motion + grip only** — feeding
perception/pose from a simulated camera frame is a separate, still-open
problem (`contracts/sim_scene_capture.md`; the sim's `GET_ZIVID_DATA`
command is unimplemented), unaffected by `robot_target`.

## Auth (`orchestrator/auth.py`, `orchestrator/config.py`)

The orchestrator is **both enforcer and caller** for the shared-token auth
scheme (see [ADR 0009](../Decisions/0009-shared-token-auth.md)):

- **Enforcer**: `POST /run` and `GET /events/run` (see "Entry points" below)
  carry `dependencies=[Depends(require_token)]` — `orchestrator/auth.py`'s
  `require_token`, the same ~35-line dependency copy-pasted into
  perception/pose/damage. Checks `WBK_API_TOKEN`; unset = no-op, so
  dry-run/tests/mocks are unaffected.
- **Caller**: `OrchestratorConfig.auth_headers` (a property, `config.py`)
  returns `{"Authorization": f"Bearer {api_token}"}` when `api_token` is set,
  else `{}`. `HttpPerception`, `HttpPose`, and `HttpDamage` (`clients/http_*.py`)
  each construct their `httpx.Client(headers=config.auth_headers)` with this
  — every outbound call to perception/pose/damage carries the same token the
  orchestrator itself requires. **`HttpMovement`/`HttpGrip` do not** — the
  teammate-owned Jetson endpoints are out of scope for this auth layer (see
  ADR 0009).
- One env var (`WBK_API_TOKEN`) has to match across every service instance
  for a real (non-dry-run) deployment; `docker-compose.yml` and the
  `deploy/*/.env.example` files pass it through to every container.

## Hand-eye calibration & the grasp chain (`orchestrator/config.py`, `orchestrator/clients/naive_grasp.py`, commit `6994503`)

`NaiveTopDownGrasp.plan()` computes the grasp pose in the robot **base
frame** by composing three SE(3) transforms (matrix `@`, not element-wise):

```
base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp
```

| Term | Source | Config |
|---|---|---|
| `cam_T_obj` | pose stage output (`Pose.T_cam_obj`, metres, OpenCV camera frame) | per-frame, from `pose.estimate()` — not config |
| `T_base_cam` | **static** hand-eye extrinsic, base←camera | env `T_BASE_CAM` (flat-16 row-major JSON); identity default |
| `obj_T_grasp` | grasp offset in the object frame (from CAD / a future real grasp planner) | env `T_OBJ_GRASP` (flat-16 row-major JSON); identity default |

Both matrices are parsed by `config._load_matrix()`, which also handles unit
conversion: if `T_BASE_CAM_UNITS=mm` (or `T_OBJ_GRASP_UNITS=mm`) is set, the
translation column is divided by 1000 before use — the pose stage's
`T_cam_obj` is always in metres (see
[Integration Points](./integration_points.md)), but calibration rigs (e.g.
Zivid hand-eye calibration) commonly output translations in mm.

Design facts (see
[ADR 0006](../Decisions/0006-eye-to-hand-static-calibration.md) for the full
rationale):
- This is **eye-to-hand** calibration — the camera is fixed to the world
  (ceiling-mounted), not to the robot flange — so `T_base_cam` is a single
  matrix solved **once**, offline, and never recomposed per frame (contrast
  with eye-in-hand, where the camera moves with the arm and the transform
  would need recomposing every frame).
- For this single, fixed robot, **base frame == world frame**, so
  `T_base_cam` alone is enough to get a camera-frame object pose into the
  frame the arm expects — no separate world↔base step.
- `obj_T_grasp` exists because the **TCP must reach the grasp point, not the
  object origin** — without it the gripper would target wherever the CAD
  origin happens to be, not a graspable feature.
- The pre-grasp pose backs off along the **grasp's own approach axis** (local
  `-z`, via `NaiveTopDownGrasp._standoff`), by `grasp_approach_dist` metres
  (env `ORCH_APPROACH_DIST`, default `0.10`).
- Both matrices default to **identity** — a placeholder that makes real
  grasps wrong, not a safe fallback. They drop in via the env vars above
  with **no code change** once the arm is calibrated and CAD grasp offsets
  are known.
- Final grasp accuracy is bounded by the **worst link in the chain**:
  calibration residuals, robot mastering error, and pose-estimate noise each
  tighten (or loosen) one link independently.

## Entry points

- **`python -m orchestrator.dry_run`** (`orchestrator/dry_run.py`) — runs the
  full loop against every mock, prints each `LoopEvent`. No services, GPU,
  weights, or hardware required. This is the primary way to prove/demo the
  integration while teammate-owned pieces are still in progress. See
  [SOP: running the orchestrator dry-run](../SOP/running_orchestrator_dry_run.md).
- **`orchestrator.app:app`** (`orchestrator/app.py`, FastAPI, port `:8000`) —
  `GET /health` (open, no token); `POST /run?dry_run=true|false&product=<id>`
  builds an orchestrator via `build_orchestrator()` and returns
  `{"stats": ..., "target": ..., "product": ..., "events": [...]}`. This is
  what `docker-compose.yml`'s `orchestrator` service runs in production
  (`dry_run=false` against the live containers + Jetson endpoints). Gated by
  `Depends(require_token)` when `WBK_API_TOKEN` is set — see "Auth" above.
  `product` (added 2026-07-08) switches to a plan-driven run — see "Plan
  mode" above; omitted or empty runs the original fixed-mode loop.
- **`GET /products`** (`orchestrator/app.py`, added 2026-07-08) — lists the
  operator-selectable products from the (mock-)ERP dataset (`{"products":
  [{"id", "name", "description", "parts": [...]}]}`), for the dashboard's
  `ProductSelector`. Reads `orchestrator/clients/erp.py`'s `load_products()`
  directly — does not involve a `PlanProvider` (no plan generation, just
  listing). Token-gated like every other work endpoint.
- **`GET /plan?product=<id>&dry_run=<bool>`** (`orchestrator/app.py`, added
  2026-07-08) — generates (but does not execute) the disassembly plan for a
  product, so an operator can preview the LLM/ERP plan before starting a
  run. Builds the same `PlanProvider` `_build_plan_provider()` would (or
  `MockPlanProvider` if `dry_run=true`); 404 (not the generic 500) on an
  unknown product, since `PlanProvider.get_plan()` raises `ValueError` for
  that case specifically. Token-gated.
- **`GET /events/run?dry_run=<bool>&delay=<seconds>&target=<real|sim|both>&product=<id>`**
  (`orchestrator/app.py`, added alongside the dashboard; `product` param
  added 2026-07-08) — the same loop, but **streamed** as Server-Sent Events
  instead of collected into one response: this is what the
  [dashboard](./dashboard.md) consumes to narrate the loop live. The loop
  runs synchronously in a daemon worker thread (`threading.Thread`, name
  `orchestrator-run`) and pushes `LoopEvent`s through a `queue.Queue` that an
  async generator drains via `loop.run_in_executor(None, q.get)` — this
  bridges the loop's blocking calls (HTTP clients, `time.sleep`) into the
  async SSE response without making `loop.py` itself async. `delay` (seconds,
  default `0.0`) sleeps in the worker thread after each event — mocks
  otherwise run to completion in milliseconds, too fast to watch live.
  Frame sequence: one `start` frame, then one `event` frame per `LoopEvent`
  (now including `PLAN_GENERATED`/`STEP`/`GUARDRAIL` in plan mode), then
  either a `summary` frame (final stats) or an `error` frame (run raised —
  surfaced to the UI instead of a silent hang/timeout), then always a
  terminal `end` frame that closes the stream. See
  [Integration Points](./integration_points.md) for the exact SSE format.
  `POST /run` is unchanged and still exists as the non-streaming variant (a
  scripted smoke test, e.g., doesn't need SSE parsing). Also gated by
  `Depends(require_token)`; since a browser `EventSource` can't set headers,
  this is the endpoint that motivated the `?token=` query-param transport
  alongside the `Authorization: Bearer` header — see "Auth" above and
  [ADR 0009](../Decisions/0009-shared-token-auth.md).
- **CORS**: `app.py` adds `CORSMiddleware` with `allow_origins=["*"]`,
  `allow_credentials=False` — required because the dashboard is a separate
  origin (see [ADR 0008](../Decisions/0008-frontend-separate-static-app.md)).
  Judged acceptable for a trusted-LAN demo control plane; tighten to the
  known dashboard origin(s) before any wider exposure.

## Data model (`orchestrator/models.py`)

Plain **dataclasses**, not pydantic — deliberate, so the orchestrator package
imports with no heavy deps and `dry_run.py`/tests run anywhere without
`httpx`/`cv2`/`numpy` installed:
`Box`, `SceneFrame` (`rgb_b64`, `depth_b64?`, `K?`), `PartDetection`
(`class_name`, `score`, `box?`, `point?`, `mask_b64?`, `id`), `Pose`
(`T_cam_obj`, `score?`, `stage?` — matches the pose stage's contract), `Grasp`
(`T_base_grasp`, `pre_grasp?`, `width?`, `meta`), `Inspection` (`verdict`,
`damaged`, `bin`, `confidence`, `issues`), `LoopEvent`, and (added
2026-07-08, the planning head — see "Plan mode" above) `PlanStep` (`part`,
`action`, `index`, `notes?`), `Plan` (`product`, `steps: list[PlanStep]`,
`source: static|llm|mock|static-fallback`, `rationale?`), and `ArmAction`
(`kind: move_named|move_to_pose|gripper`, `name?`, `pose_ref?`, `closed?`,
`width?` — the *only* shape an LLM may propose robot motion in; see
[ADR 0011](../Decisions/0011-llm-action-selector-constrained-vocabulary.md)).

## Teammate-owned contracts (`contracts/`)

Two endpoints were drafted for hardware this repo doesn't own — the Jetson
arm and the grip sensor. The orchestrator's real HTTP clients
(`HttpMovement`, `HttpGrip`) were written *against proposed contracts* so
integration didn't block on the hardware landing first. **Movement has since
landed as a real, in-repo service** (`robot_control/`, Group 2 — see
[System: Robot Control](./robot_control.md) and
[ADR 0010](../Decisions/0010-robot-control-integration.md)), but its actual
API is richer/different from the draft below, and `HttpMovement` has **not**
been adapted to it yet — treat the movement contract text below as the
target `HttpMovement` still speaks, not what the real service exposes. Grip
remains fully external:

- [`contracts/movement_api.md`](../../contracts/movement_api.md) — `POST
  /move_to_pose` (4x4 base-frame pose), `POST /move_named` (named poses:
  `home`, `clearance`, `inspect_0..N`, `ok_bin`, `reject_bin`), `POST
  /gripper` (`closed`, `width?`), optional `GET /state`. Synchronous — calls
  return only once motion completes. As of commit `e0a1b13`, `/gripper`
  close must additionally **block until the gripper settles/stalls** — the
  grip-current read that follows (see next bullet) needs a steady-state, not
  inrush, value. Default `MOVEMENT_URL=http://jetson.local:9000`.
- [`contracts/grip_api.md`](../../contracts/grip_api.md) — `GET /grip` →
  `{"grasped": bool, "current": float, "width"?: float, "threshold"?: float}`
  (boolean-only `{"grasped": bool}` / `{"raw": 0|1}` still accepted), polled
  right after gripper close. As of commit `e0a1b13`, grip sensing is
  **motor-current-based**, not a binary pad — see
  [ADR 0007](../Decisions/0007-grip-motor-current-sensing.md) for the
  end-stop false-positive pitfall the contract designs around. Default
  `GRIP_URL=http://jetson.local:9001`.

**REST approach confirmed, and the movement adapter has now landed
(2026-07-07).** A hardware teammate confirmed the robot-arm movement/grip
control interface would be an HTTP-adapter microservice, to be uploaded to
this repo shortly. This had been in doubt: an earlier inspection of the
Jetson controller found it running NeuraPy (NEURA's Python SDK) with no REST
API of its own — only a read-only joint-state TCP publisher on `:5005` and a
localhost MJPEG stream — which cast doubt on whether `HttpMovement`/`HttpGrip`'s
REST contracts were the right shape. That doubt is resolved and the
microservice has arrived as **`robot_control/`** (Group 2's Jetson bridge,
merged commit `604733a`) — see [System: Robot Control](./robot_control.md).
It is an HTTP FastAPI service, as expected, but it talks to the arm over a
raw **TCP socket** to a separate LARA5/NEURA robot socket server (not itself
in this repo), and exposes a richer, differently-shaped API
(`/robot/hover/plan`, `/robot/hover/execute`, `/robot/execute/`, `/robot/raw`,
calibration endpoints) than the flat `move_to_pose`/`move_named`/`gripper`
shape `contracts/movement_api.md` drafted. `HttpMovement` has **not** been
aligned to it yet — see [ADR 0010](../Decisions/0010-robot-control-integration.md)
"Open gap" for exactly what's blocking that (pose-vector/frame convention
confirmation from the robot team) and what the adapter work will involve.
The grip endpoint (`contracts/grip_api.md`) remains fully unimplemented.

Both contract files are drafts — the note in each file is explicit that the
hardware teammate should adjust freely and the client will follow. **Grasp planning**
itself (`NaiveTopDownGrasp`) is also explicitly a placeholder, not a
teammate-owned contract — same file, `orchestrator/clients/naive_grasp.py` —
top-down grasp at the object origin with a fixed stand-off, no gripper
geometry or approach reasoning. Swap it out when the real planning module
lands; the `GraspPlanner` Protocol is the seam.

## Two future VLM roles (seams only, not implemented)

The task spec calls for two additional VLM-driven behaviors. Both have a
clean seam already in place in the Protocol design, but neither is
implemented:

1. **VLM next-part selection** — pick the next part to disassemble from a
   part description or free-text prompt, rather than (or in addition to)
   LocateAnything's current text-query grounding. Slots in as an alternative
   `PerceptionClient.next_part` backend — no loop changes needed.
2. **VLM grip verification** — a visual check (via the inspection or scene
   camera) that the *correct* part was grasped, run **alongside** the grip
   sensor as a second opinion. As of commit `e0a1b13` the grip sensor itself
   is motor-current-based (`grasped` plus analog `current`/`width`, see
   [ADR 0007](../Decisions/0007-grip-motor-current-sensing.md)), which
   already gives a partial-grip signal the old binary pad couldn't — but it
   still can't distinguish "gripped the *wrong* part" from "gripped
   correctly"; a VLM check adds that semantic/geometric judgment. Would need
   a new `GripVerifier` Protocol, ANDed with `GripSensor` inside
   `_grasp_with_retry`. Noted in `orchestrator/README.md`, "Future" — do not
   assume any code for this exists.

## Tests

[`tests/orchestrator/test_loop.py`](../../tests/orchestrator/test_loop.py) —
5 tests, the full loop driven entirely by mocks (no `httpx`/`cv2`/`numpy`
required): full disassembly + correct bin sort, the rectify-retry path fires
on a failed grip read, a damaged part routes to `reject_bin`, an ungraspable
part is blacklisted and the loop stops cleanly (not a runaway), and the loop
terminates within `max_steps`.

[`tests/orchestrator/test_auth.py`](../../tests/orchestrator/test_auth.py) —
7 tests covering `require_token` wired onto `POST /run`/`GET /events/run`:
disabled when `WBK_API_TOKEN` unset, 401 on missing/wrong token, accepted via
both the `Authorization: Bearer` header and the `?token=` query param,
`GET /health` stays open regardless. Mirrored by 4-test `test_auth.py` files
in each of `tests/{damage,perception,pose}/` for their own `require_token`
copies.

[`tests/orchestrator/test_plan.py`](../../tests/orchestrator/test_plan.py) —
24 tests (added 2026-07-08) covering the planning head end to end:
`validate_actions()`'s full rejection surface (unknown kind, out-of-context
named pose, bad `pose_ref`, stray fields, too many actions, missing/extra
terminal gripper-close), `scripted_grasp_sequence()`/`execute_actions()`,
`StaticPlanProvider`/`LlmPlanProvider` (permutation guardrail, static
fallback on any LLM/API error, unknown-product `ValueError`), `_run_planned`
(SKIP on an unlocated part, BLOCKED on an unresolvable grasp, `STEP`/
`PLAN_GENERATED` event shapes), and the `GUARDRAIL` fallback path via
`MockActionSynthesizer(bad=True)`. Suite total is now **204** (see
[Architecture](./architecture.md) and
[SOP: running the tests](../SOP/running_tests.md)).

[`tests/orchestrator/test_robot_target.py`](../../tests/orchestrator/test_robot_target.py)
(9 tests) and
[`tests/orchestrator/test_sim_movement.py`](../../tests/orchestrator/test_sim_movement.py)
(13 tests) — added alongside "Robot target selection" above, already
included in the 204 total. `test_robot_target.py` covers `_build_robot()`'s
real/sim/both selection (right URLs, `SimGrip` vs. `HttpGrip` for the sim
grip endpoint, the `MOVEMENT_SIM_URL`-missing and unknown-target `ValueError`
cases) and `TeeMovement`'s fan-out semantics (every call reaches both
backends, a primary error propagates, a mirror error is swallowed and
reported via the callback, never raised).
`test_sim_movement.py` exercises `IsaacSimMovement` against an
`httpx.MockTransport` standing in for the Isaac command bus: the
matrix→position/quaternion math (identity, translation, two rotations, unit
quaternion), the `move_to_pose`/`move_named`/`set_gripper` → sim-action
mapping, the `SIM_NAMED_POSES` env override, and the command lifecycle
(`failed` status raises, a command that never reaches a terminal status
times out). No `frontend/` Vitest coverage exists yet for the new
`SceneView`/`SourceToggle`/`PartSelector` components or the rewritten
`PerceptionPage.tsx` capture/inference flow — see
[System: Dashboard](./dashboard.md) "Test suite".
