# Orchestrator — the disassembly state machine

## Related Docs
- [Architecture](./architecture.md) — full pipeline overview, per-stage service map
- [Integration Points & Wire Contracts](./integration_points.md) — perception/pose/damage wire contracts the orchestrator's HTTP clients speak
- [ADR: mock-first, interface-seam integration](../Decisions/0005-mock-first-interface-seam-integration.md) — why the loop was built against Protocols + mocks before teammate-owned hardware existed
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

## The loop (`orchestrator/loop.py`, `DisassemblyOrchestrator.run()`)

Per part, in order:

```
LOCATE   perception.next_part(frame)         — next part to remove (None => done)
  │        blacklist check: a part that already failed max attempts stops the loop
POSE     pose.estimate(frame, part)          — 6DoF T_cam_obj
PLAN     grasp.plan(pose, part)              — grasp pose in base frame
GRASP    _grasp_with_retry(...):
           move.move_to_pose(pre_grasp); move.move_to_pose(grasp)
           move.set_gripper(closed=True)
           grip.is_grasped()  ── sensor=0 ──► grasp.replan(...); retry
                               (up to config.max_grasp_attempts, default 3)
           sensor=1 ──► confirmed, continue
REMOVE   move.move_named("clearance")        — lift clear
         perception.is_present(after, part)  — confirm it's actually gone
           still present => wrong/failed grab: release, retry from LOCATE
INSPECT  present to inspection_camera for config.inspection_angles angles
         damage.inspect(images, part)        — OK/damaged verdict
SORT     move.move_named(inspection.bin); drop; move.move_named("home")
         repeat until perception.next_part() returns None, or a part is blacklisted
```

**"Rectify grabbing mistakes"** (one of the three product jobs — see
[Architecture](./architecture.md)) lives entirely in `_grasp_with_retry`: the
binary grip sensor gates progress and a failed read (`sensor=0`) triggers a
re-planned retry, not just a repeat of the same grasp. A part that never
confirms a grasp after `max_grasp_attempts` gets **blacklisted** (`blacklist:
set[str]` in `run()`) so a single ungraspable part can't spin the loop
forever — the loop emits `BLOCKED` and stops for an operator instead.

Every step emits a `LoopEvent` (`step`, `state`, `message`, `data`) — states
are `LOCATE`, `POSE`, `GRIP`, `REGRASP`, `SKIP`, `REMOVE`, `RECHECK`,
`INSPECT` (implicit via `SORT`), `SORT`, `BLOCKED`, `DONE`, `SUMMARY`. These
drive both the demo narration (`dry_run.py` prints them) and the FastAPI
response (`app.py` collects them into `events: list[dict]`).

## The Protocol seam (`orchestrator/clients/base.py`)

The orchestrator depends **only on Protocol interfaces**, never on concrete
implementations:

| Protocol | Real client | Talks to |
|---|---|---|
| `SceneCamera` | `StaticSceneCamera` (`clients/cameras.py`) | file/RGB-D source (RealSense TODO) |
| `PerceptionClient` | `HttpPerception` (`clients/http_perception.py`) | yolo `:8001` / sam3 `:8002` / locateanything `:8003` |
| `PoseClient` | `HttpPose` (`clients/http_pose.py`) | foundationpose `:8004` (configurable) |
| `GraspPlanner` | `NaiveTopDownGrasp` (`clients/naive_grasp.py`) | local, no network — placeholder only |
| `MovementClient` | `HttpMovement` (`clients/http_movement.py`) | **Jetson arm endpoint** (teammate-owned, external) |
| `GripSensor` | `HttpGrip` (`clients/http_grip.py`) | **binary pressure sensor** (teammate-owned, external) |
| `InspectionCamera` | `OpenCVInspectionCamera` (`clients/cameras.py`) | inspection webcam |
| `DamageClient` | `HttpDamage` (`clients/http_damage.py`) | damage service `:8006` |

Every Protocol also has a mock in `orchestrator/mocks.py` (`MockSceneCamera`,
`MockPerception`, `MockPose`, `MockGraspPlanner`, `MockMovement`, `MockGrip`,
`MockInspectionCamera`, `MockDamage`) — parameterized so tests and the
dry-run can drive specific scenarios (e.g. `MockGrip(fail_first=True)` to
exercise the rectify-retry path, `MockDamage(damaged_classes={"gear"})` to
exercise the reject bin).

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
`http://jetson.local:9001`); behavior knobs `MAX_GRASP_ATTEMPTS` (default 3),
`MAX_STEPS` (default 50, the runaway-loop bound), `INSPECTION_ANGLES`
(default 3); and `T_BASE_CAM`, the camera→base extrinsics (flat-16 JSON env
var, identity default) the naive grasp planner uses to transform
`T_cam_obj` into the robot base frame.

## Entry points

- **`python -m orchestrator.dry_run`** (`orchestrator/dry_run.py`) — runs the
  full loop against every mock, prints each `LoopEvent`. No services, GPU,
  weights, or hardware required. This is the primary way to prove/demo the
  integration while teammate-owned pieces are still in progress. See
  [SOP: running the orchestrator dry-run](../SOP/running_orchestrator_dry_run.md).
- **`orchestrator.app:app`** (`orchestrator/app.py`, FastAPI, port `:8000`) —
  `GET /health`; `POST /run?dry_run=true|false` builds an orchestrator via
  `build_orchestrator()` and returns `{"stats": ..., "events": [...]}`. This
  is what `docker-compose.yml`'s `orchestrator` service runs in production
  (`dry_run=false` against the live containers + Jetson endpoints).

## Data model (`orchestrator/models.py`)

Plain **dataclasses**, not pydantic — deliberate, so the orchestrator package
imports with no heavy deps and `dry_run.py`/tests run anywhere without
`httpx`/`cv2`/`numpy` installed:
`Box`, `SceneFrame` (`rgb_b64`, `depth_b64?`, `K?`), `PartDetection`
(`class_name`, `score`, `box?`, `point?`, `mask_b64?`, `id`), `Pose`
(`T_cam_obj`, `score?`, `stage?` — matches the pose stage's contract), `Grasp`
(`T_base_grasp`, `pre_grasp?`, `width?`, `meta`), `Inspection` (`verdict`,
`damaged`, `bin`, `confidence`, `issues`), `LoopEvent`.

## Teammate-owned contracts (`contracts/`)

Two endpoints are **not built in this repo** — they're owned by teammates
working on the Jetson arm and the grip hardware. The orchestrator's real
HTTP clients (`HttpMovement`, `HttpGrip`) were written *against proposed
contracts* so integration doesn't block on the hardware landing first:

- [`contracts/movement_api.md`](../../contracts/movement_api.md) — `POST
  /move_to_pose` (4x4 base-frame pose), `POST /move_named` (named poses:
  `home`, `clearance`, `inspect_0..N`, `ok_bin`, `reject_bin`), `POST
  /gripper` (`closed`, `width?`), optional `GET /state`. Synchronous — calls
  return only once motion completes. Default `MOVEMENT_URL=http://jetson.local:9000`.
- [`contracts/grip_api.md`](../../contracts/grip_api.md) — `GET /grip` →
  `{"grasped": bool}` or `{"raw": 0|1}` (either accepted), polled right after
  gripper close. Default `GRIP_URL=http://jetson.local:9001`.

Both are drafts — the note in each file is explicit that the hardware
teammate should adjust freely and the client will follow. **Grasp planning**
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
   camera) that the *correct* part was grasped, run alongside the binary
   0/1 pressure sensor as a second opinion. The binary sensor can't
   distinguish "gripped the wrong part" or "partial grip" from "gripped
   correctly" — a VLM check would catch that. Would need a new
   `GripVerifier` Protocol, ANDed with `GripSensor` inside
   `_grasp_with_retry`. Noted in `orchestrator/README.md`, "Future" — do not
   assume any code for this exists.

## Tests

[`tests/orchestrator/test_loop.py`](../../tests/orchestrator/test_loop.py) —
5 tests, the full loop driven entirely by mocks (no `httpx`/`cv2`/`numpy`
required): full disassembly + correct bin sort, the rectify-retry path fires
on a failed grip read, a damaged part routes to `reject_bin`, an ungraspable
part is blacklisted and the loop stops cleanly (not a runaway), and the loop
terminates within `max_steps`. Suite total is now **86** (see
[Architecture](./architecture.md) and
[SOP: running the tests](../SOP/running_tests.md)).
