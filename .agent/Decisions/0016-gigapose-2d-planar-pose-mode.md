# ADR 0016: GigaPose gains a CAD-free, model-free 2D (planar) pose mode, with graceful startup degrade

## Related Docs
- [System: Architecture](../System/architecture.md) — Stage 2 6DoF Pose, `pipeline` options table
- [System: Integration Points](../System/integration_points.md) — Contract 2 (`POST /pose`), the `pipeline='2d'` addition
- [SOP: deploying the pose services (podman)](../SOP/deploy_pose_podman.md) — the deployed reality this mode was built for (no CAD templates on the running `wbk-gigapose`)
- [ADR 0004: pose contract reuses kip-pose-viewer](./0004-pose-contract-reuses-kip-pose-viewer.md) — the `T_cam_obj` contract this mode is a drop-in for
- [ADR 0001: perception shared container vs. pose split containers](./0001-perception-shared-container-pose-split-containers.md) — why `gigapose` is its own container/model in the first place

## Status
Accepted (2026-07-08, commit `79f9ffa`, deploy script `f2a5da8`).

## Context

The deployed `wbk-gigapose` service has **no CAD templates for this
project's parts** (`GigaPoseRunner.classes` reads the class→objId map off
the loaded adapter and returns `[]` when none is registered — see
`pose/gigapose_svc/model.py`). GigaPose's 6DoF pipelines (`rgb`/`rgbd`)
require 162 pre-rendered templates per object *before* the service starts
(see [SOP: running the services](../SOP/running_services.md) and ADR 0004's
"fragile bits"); building those templates needs CAD meshes for every
disassembly part, which do not exist for this project today. Net effect:
**6DoF pose estimation cannot run against real parts right now**, regardless
of code correctness — this is an asset gap, not a bug.

The team's live loop still needs *some* pose for real picking, though. Two
paths were available:
1. Block on producing CAD meshes + templates for all parts before any
   pose-driven picking demo works.
2. Build a pose mode that needs no CAD/templates at all, using only what
   perception already reliably produces: a segmentation mask (from
   `yoloseg`/`sam3`) and the camera intrinsics/depth already flowing through
   the pipeline.

The KIP seminar's `detect_and_move` reference (bbox/mask centroid + depth ->
world point, fixed top-down approach) was the inspiration for path 2 — it
already solves "where is the part" for flat, top-down picking without any
model. This project's parts are disassembly components handled from above,
so a top-down grasp is a reasonable default; a bare centroid-only version
was judged too weak, since with no in-plane rotation every gripper approach
lands at a fixed orientation regardless of how the part is actually rotated
on the table, which fails for elongated/asymmetric parts. Enriching it with
an in-plane yaw from the mask's own principal axis (PCA) closes that gap
cheaply.

A second question: what happens to service **startup** when the 6DoF model
fails or is simply unwanted for a fast demo boot. Before this change,
`GigaPoseRunner.load()` failing (or being slow — template loading is not
instant) blocked the FastAPI lifespan, so a partial/CAD-less deployment
couldn't serve *any* pose, including the new CAD-free mode.

## Decision

1. Added `pose/shared/planar.py`'s `planar_pose()`: numpy-only geometry that
   back-projects the mask centroid to a 3D point (depth priority: per-mask
   median depth from the depth image -> caller-supplied `plane_z` -> a
   built-in `default_z=0.5`m, `stage` records which was used: `2d` /
   `2d-plane` / `2d-defaultz`) and builds a top-down rotation
   `R = Rz(theta) @ Rx(pi)` where `theta` is the mask's PCA principal-axis
   angle in image space. `score` is the mask's fill-ratio of its own
   bounding box (a cheap segmentation-quality proxy, not a pose-confidence
   number). Output is the exact same `T_cam_obj` (4x4, object->camera,
   OpenCV frame, metres) as the 6DoF pipelines — see ADR 0004 — so it is a
   **drop-in**: the orchestrator's `HttpPose` client and the dashboard's
   pose overlay need no changes to consume `pipeline='2d'` poses.
2. Added `pipeline='2d'` as a third value on `PoseRequest.pipeline` (was
   `'rgbd'`/`'rgb'`) plus an optional `plane_z: float | None` field, both in
   `pose/shared/schemas.py`. `pose/gigapose_svc/app.py`'s `/pose` route
   branches to `planar_pose()` for `pipeline='2d'` and bypasses
   `GigaPoseRunner` entirely — no GPU inference, no template lookup.
   `foundationpose` does not gain this mode; it stays 6DoF-only (there was
   no equivalent asset gap forcing FoundationPose into a fallback path in
   this pass).
3. `gigapose_svc/app.py`'s lifespan now wraps `runner.load()` in a
   try/except: a failed/skipped 6DoF load logs a message and lets the
   service start anyway, serving `pipeline='2d'` only. A subsequent
   `pipeline='rgb'`/`'rgbd'` request against an unloaded runner now returns
   **503 with an explicit message** ("6DoF model not loaded; use
   pipeline='2d'") instead of the service failing to come up at all.

## Why

- **Unblocks real picking today without CAD assets.** The alternative
  (path 1 above) gates every real-part demo on producing and rendering
  templates for every disassembly part — asset work with no code
  dependency, and not guaranteed to finish before a hackathon deadline. The
  2D mode turns "no CAD templates" from a hard blocker into a documented
  capability gap (6DoF unavailable, 2D available).
- **Reuses what's already reliable.** `yoloseg`/`sam3` masks are trained,
  deployed, and verified (see `System/training.md`, ADR 0012); pose only
  needs to turn a mask + depth into a pick pose, which is exactly what
  `detect_and_move`'s approach already does elsewhere in the KIP ecosystem.
  No new model, no new weights, no new container dependency — `planar.py`
  is pure numpy.
- **Same contract, zero blast radius on consumers.** Because `T_cam_obj`'s
  shape/frame/units are unchanged (ADR 0004), the orchestrator's grasp
  chain (`base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp`) and the
  frontend's pose visualization work against `pipeline='2d'` output with no
  branching on which pipeline produced it — the same reasoning ADR 0004
  used to justify sharing one contract across FoundationPose/GigaPose in
  the first place.
- **Graceful degrade over hard startup dependency.** A service that
  0/false-starts because one optional capability (6DoF) isn't asset-ready
  is strictly worse than one that starts and clearly reports which pipeline
  it can serve. The 503 on the unavailable pipeline is explicit and
  actionable (unlike a service that's simply down), and costs nothing when
  the 6DoF model *is* loaded normally — the try/except only changes
  behavior on failure.
- **Top-down + PCA-yaw over bare centroid-only.** A fixed-orientation
  centroid pose (no in-plane rotation) was judged too weak for anything but
  perfectly axis-aligned parts; PCA on the mask pixels is a few lines of
  numpy and costs no extra service round-trip, so there was no reason to
  ship the weaker version first.

Rejected alternatives:
- **Block on CAD/template production before demoing real picking** —
  rejected as a hackathon-timeline risk with no code payoff.
- **A second full contract/response shape for the CAD-free mode** —
  rejected; reusing `PoseRequest`/`ObjectPose` verbatim (new `pipeline`
  enum value + one optional field) is strictly simpler than a parallel
  schema, and preserves the drop-in property above.
- **Hard-fail startup on missing 6DoF model** (the prior behavior) —
  rejected once it became clear the deployed instance would never have
  templates in the short term; a service that can't start is strictly worse
  than one serving a documented subset.

## Consequences

- **`classes: []` is expected, not a bug**, on any GigaPose deployment with
  no CAD/template assets loaded — `GET /health`'s `classes` field will be
  empty, and any `pipeline='rgb'`/`'rgbd'` request will 503. This is the
  current state of the deployed `wbk-gigapose` instance — see
  [SOP: deploying the pose services (podman)](../SOP/deploy_pose_podman.md).
- **2D mode is planar/top-down only** — it has no way to recover object tilt
  or express anything other than a flat table-top yaw. It is not a
  general-purpose 6DoF replacement; it's a fallback for flat, top-down
  picking specifically, which matches this project's disassembly-part
  handling but would not suit e.g. picking a part out of a bin at an
  arbitrary angle.
- `score` for 2D-mode poses means something different from GigaPose's own
  `score` (coarse-match confidence) — it's a mask fill-ratio. A downstream
  consumer that compares scores across pipelines without checking `stage`
  first would be comparing two different quantities.
- Verified end-to-end against real YOLO-Seg masks (post the mask-encoding
  fix below): 3 poses in 55ms, distinct per-part yaw, `stage='2d-plane'`.
  Not yet verified: real-robot grasp success using 2D-mode poses (this ADR
  covers the pose-service change only, not a grasp-execution evaluation).
