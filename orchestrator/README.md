# Orchestrator

The **disassembly state machine** — the connective tissue that runs the whole
loop by calling every stage through pluggable clients. It exists so the pipeline
can be built and demoed **now**, while YOLO detection, the Jetson movement
endpoint, and the grip sensor are still being built by teammates: we run against
mocks today and swap in real clients as they land, with no change to the loop.

## The loop (per part)

```
LOCATE   perception: next part to remove  (LocateAnything text query)
  │
POSE     6DoF pose of the target          (foundationpose / gigapose)
  │
PLAN     grasp pose from the 6DoF pose     (naive planner for now)
  │
GRASP    move → close → read grip sensor   ── sensor=0 ─► REGRASP (re-plan, retry)
  │  sensor=1                                     (rectify grabbing mistakes)
REMOVE   lift clear, confirm the part is actually gone (SAM3 before/after)
  │
INSPECT  present to webcam (N angles) → damage VLM → verdict
  │
SORT     place in ok_bin / reject_bin
  └────► repeat until nothing remains
```

The **"rectify grabbing mistakes"** product goal lives in `_grasp_with_retry`
(loop.py): the binary grip sensor gates progress and a failed read triggers a
re-planned retry; a part that can't be grasped is blacklisted so it can't spin
the loop forever.

## Run the dry-run (no services/hardware)

```bash
python -m orchestrator.dry_run     # from repo root
```

Every stage is mocked; the first grasp deliberately fails to show the rectify
retry, and one part is "damaged" to show the reject bin. Example output:

```
[ 1] LOCATE   next part: cover
[ 1] POSE     6DoF pose for cover
[ 1] REGRASP  grasp attempt 1 failed (sensor=0), re-planning
[ 1] GRIP     grasp confirmed (sensor=1) on attempt 2
[ 1] REMOVE   lifted cover clear
[ 1] SORT     cover: ok -> ok_bin
...
[ 4] DONE     assembly fully disassembled
```

## As a service

`orchestrator.app:app` exposes `GET /health` and `POST /run?dry_run=true|false`
(port 8000). A real run drives the live services + teammate endpoints.

## Interfaces (`clients/base.py`)

The loop depends only on Protocols; each has a mock (`mocks.py`) and a real
client (`clients/`):

| Protocol | Real client | Talks to |
|---|---|---|
| `SceneCamera` | `StaticSceneCamera` | file/RGB-D source (RealSense TODO) |
| `PerceptionClient` | `HttpPerception` | yolo/sam3/locateanything |
| `PoseClient` | `HttpPose` | foundationpose/gigapose |
| `GraspPlanner` | `NaiveTopDownGrasp` | (local; real module TODO) |
| `MovementClient` | `HttpMovement` | **Jetson endpoint** — [contract](../contracts/movement_api.md) |
| `GripSensor` | `HttpGrip` | **pressure sensor** — [contract](../contracts/grip_api.md) |
| `InspectionCamera` | `OpenCVInspectionCamera` | inspection webcam |
| `DamageClient` | `HttpDamage` | damage service |

The two teammate-owned endpoints have **proposed contracts** in
[`../contracts/`](../contracts/) — hand those over so everyone builds to the same
shape.

## Future (from the task spec — noted, not yet built)

Two VLM roles the challenge calls for, with clean seams already in place:

1. **VLM next-part selection** — identify the next part to disassemble from a
   **part description or a prompt**. Slots in as an alternative `PerceptionClient.
   next_part` backend (today it's LocateAnything). No loop changes needed.
2. **VLM grip verification** — a visual check that the grip is correct, running
   **alongside** the grip sensor in `_grasp_with_retry` as a second opinion. The
   grip sensor is motor-current-based (see `contracts/grip_api.md`), so its analog
   `current`/`width` already give a *partial-grip* signal; the VLM adds the
   semantic/geometric "is it the **right** part, gripped squarely" judgment the
   current can't. Add a `GripVerifier` protocol and AND it with `GripSensor`.

Also future: a real grasp-planning module (replacing `NaiveTopDownGrasp`) and an
RGB-D scene-camera client.

## Hand-eye calibration

The grasp chain converts a camera-frame object pose to a robot-base grasp pose:

```
base_T_grasp = T_base_cam · cam_T_obj · obj_T_grasp
```

- `cam_T_obj` — object pose from the pose stage (camera frame, metres).
- **`T_base_cam`** — the hand-eye extrinsic, **eye-to-hand** (camera fixed to the
  world / ceiling), so a single **static** 4×4 solved once by calibration — never
  recomposed per frame. Supply it as `T_BASE_CAM` (flat-16 row-major JSON,
  `base←camera`). If your calibration outputs mm (e.g. Zivid), set
  `T_BASE_CAM_UNITS=mm` and it's converted to metres to match the pose stage.
  Until provided it defaults to **identity**, which makes grasps wrong.
- `obj_T_grasp` — grasp offset in the object frame (from CAD / the grasp planner),
  via `T_OBJ_GRASP`; defaults to identity (grasp at the object origin).

These are SE(3) matrix compositions (`@`), not element-wise. For a single fixed
robot the base frame *is* the world frame, so `T_base_cam` is all that's needed.
Final grasp accuracy is bounded by the worst link in the chain (calibration
residuals, robot mastering, and pose-estimate noise each tighten one link).

Calibration matrices will be provided after the arm is calibrated; they drop into
`T_BASE_CAM` / `T_OBJ_GRASP` with no code change.

## Layout

```
models.py     dataclasses passed between stages
config.py     env-driven URLs + behaviour knobs
clients/
  base.py       Protocols (the seams)
  http_*.py     real clients (perception, pose, damage, movement, grip)
  cameras.py    scene + inspection camera clients
  naive_grasp.py  placeholder grasp planner
mocks.py      mock every stage — powers the dry-run + tests
loop.py       the state machine
factory.py    build from mocks or real clients
dry_run.py    `python -m orchestrator.dry_run`
app.py        FastAPI wrapper (:8000)
```
