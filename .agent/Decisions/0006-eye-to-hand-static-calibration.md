# ADR 0006: Eye-to-hand static calibration + grasp chain composition

## Related Docs
- [System: Orchestrator](../System/orchestrator.md) — "Hand-eye calibration & the grasp chain" section this ADR justifies
- [System: Integration Points & Wire Contracts](../System/integration_points.md) — `T_cam_obj` units/frame convention the calibration chain must match
- [ADR: mock-first, interface-seam integration](./0005-mock-first-interface-seam-integration.md) — the Protocol-seam philosophy this decision follows (config-driven swap-in, no code change)

## Status

Accepted (commit `6994503`, 2026-07-07).

## Context

`NaiveTopDownGrasp` (`orchestrator/clients/naive_grasp.py`) needs to turn the
pose stage's output — `cam_T_obj`, an object pose in the **camera frame**
(see [Integration Points](../System/integration_points.md)) — into a grasp
pose the robot arm can execute, which must be in the **robot base frame**.
Three facts about the actual hardware setup shape how this has to work:

- The scene camera is **ceiling-mounted**, not wrist-mounted — this is an
  **eye-to-hand** rig, not eye-in-hand.
- The team has a single, fixed robot, so there is no separate "world" frame
  to reconcile — base frame and world frame are the same thing.
- The pose stage always emits `T_cam_obj` in **metres**, but the calibration
  hardware the team will use (Zivid hand-eye calibration) commonly outputs
  extrinsics with translations in **millimetres**.
- The object's own origin (from CAD/pose estimation) is not necessarily a
  graspable point — the gripper needs to reach a specific offset from it,
  not the origin itself.

The calibration matrices themselves were not available yet at the time this
was written (commit `6994503`) — the goal was to get the *seam* right so the
real matrices drop in later with zero code change.

## Decision

Model the runtime grasp-pose computation as a chain of three SE(3) matrix
compositions (`@`, not element-wise):

```
base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp
```

- **`T_base_cam`** (env `T_BASE_CAM`, flat-16 row-major JSON) is the
  eye-to-hand extrinsic, loaded once as a **static** matrix — never
  recomposed per frame, because the camera never moves relative to the
  world. This is a direct consequence of it being eye-to-hand rather than
  eye-in-hand: an eye-in-hand rig would need the *current* flange pose
  composed in on every frame; eye-to-hand needs the extrinsic solved exactly
  once.
- Since base == world for this single fixed robot, `T_base_cam` alone is
  sufficient — no separate world→base step is needed.
- **Unit conversion is explicit, not assumed.** `config._load_matrix()`
  accepts an optional `*_UNITS` env var (`T_BASE_CAM_UNITS`,
  `T_OBJ_GRASP_UNITS`); if set to `mm`, the translation column is divided by
  1000 before the matrix is used, so a raw Zivid-calibration output can be
  dropped in as-is alongside the flag, without a manual pre-conversion step.
- **`obj_T_grasp`** (env `T_OBJ_GRASP`) is a separate term specifically to
  carry the "TCP goes to the grasp point, not the object origin" offset —
  kept as its own composable matrix (from CAD or a future real grasp
  planner) rather than folded into the pose stage's contract, so the pose
  stage's output stays a pure object-pose measurement.
- Both `T_base_cam` and `obj_T_grasp` default to **identity** when their env
  vars are unset — a deliberately *wrong* default (grasps at the camera
  origin / object origin) rather than a "safe" no-op, so a missing
  calibration is visibly broken instead of silently plausible.
- Pre-grasp stand-off (`grasp_approach_dist`, env `ORCH_APPROACH_DIST`,
  default `0.10` m) is applied along the **grasp's own local `-z`** (the
  approach axis), not the camera's or base's axis — so the stand-off is
  correct regardless of grasp orientation.

## Consequences

- Once the arm is calibrated and CAD grasp offsets are known, the real
  matrices drop into `T_BASE_CAM` / `T_OBJ_GRASP` (plus the `*_UNITS` flags
  if needed) with **zero code change** — consistent with the
  config/Protocol-seam philosophy already established in
  [ADR 0005](./0005-mock-first-interface-seam-integration.md).
- Because `T_base_cam` is solved once and cached as a static matrix, if the
  camera mount is ever bumped or re-installed, the system has **no way to
  detect or self-correct** — recalibration must be re-run manually and the
  env var updated. There is no online/per-frame correction path.
- The mm/m unit mismatch is a classic silent-bug source: if `T_BASE_CAM` is
  supplied in mm without setting `T_BASE_CAM_UNITS=mm`, the matrix still
  parses and loads without error — the translation is simply wrong by a
  factor of 1000. The `_load_matrix()` conversion only helps if the flag is
  set correctly; this is a manual step, not something the code can verify.
- Final grasp accuracy is bounded by the **worst link in the chain**
  (calibration residual, robot mastering error, pose-estimate noise) — this
  is stated explicitly in the orchestrator docs so nobody assumes the chain
  is more precise than its weakest input.

## Alternatives considered

- **Eye-in-hand calibration** (camera mounted on the flange): rejected — not
  a design preference, but a hardware constraint. The actual camera is
  ceiling-mounted. Eye-in-hand would additionally require composing the
  live flange pose into the chain on every frame, which the eye-to-hand
  setup avoids entirely.
- **Hardcoding `T_base_cam` as a constant in code** instead of an env var:
  rejected — would require a code change and redeploy every time the
  arm/camera is recalibrated (e.g. after a mount is bumped), breaking the
  "swap in with no code change" goal.
- **Folding `obj_T_grasp` into the pose stage's own output** (having the
  pose service return a grasp pose directly): rejected — the pose contract
  is deliberately shared verbatim with the KIP `kip-pose-viewer` reference
  (see [ADR 0004](./0004-pose-contract-reuses-kip-pose-viewer.md)) and
  returns only an object pose; keeping the grasp-offset composition in the
  orchestrator keeps that contract untouched and swappable between
  FoundationPose/GigaPose.
