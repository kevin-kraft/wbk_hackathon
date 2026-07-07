# Proposed contract — Jetson arm movement endpoint

*Draft for the Jetson/movement teammate — adjust to what the arm SDK exposes, and
the orchestrator's `HttpMovement` client will follow.*

Base URL configured via `MOVEMENT_URL` (default `http://jetson.local:9000`).
All calls are synchronous: **return only once the motion has completed** (or error).

## `POST /move_to_pose`
Move the tool center point (TCP) to a Cartesian pose.

```jsonc
// request
{ "pose": [[..4x4..]], "frame": "base", "speed": 0.2 }   // 4x4 row-major, metres; speed optional (0..1)
// response
{ "ok": true, "reached_pose": [[..4x4..]] }
```

## `POST /move_named`
Move to a pre-taught named pose. The orchestrator uses these names:

| name | meaning |
|---|---|
| `home` | safe neutral pose |
| `clearance` | lift the just-grasped part clear of the assembly |
| `inspect_0`, `inspect_1`, … | present the held part to the inspection webcam, one per angle |
| `ok_bin` | above the working-parts bin |
| `reject_bin` | above the damaged-parts bin |

```jsonc
{ "name": "inspect_0" }            // request
{ "ok": true }                     // response
```

## `POST /gripper`
Open/close the gripper.

```jsonc
{ "closed": true, "width": 0.04 }  // width metres, optional; ignored on open
{ "ok": true, "closed": true }
```

**Close must block until the gripper settles/stalls** — the orchestrator reads the
current-based grip sensor (`grip_api.md`) immediately after, and needs a
steady-state (not inrush) reading. If the gripper reports position, returning
`width` here helps the grip sensor disambiguate held-vs-end-stop.

## `GET /state` (optional, nice to have)
```jsonc
{ "tcp_pose": [[..4x4..]], "joints": [..], "moving": false }
```

## Notes
- The number of `inspect_*` poses = the orchestrator's `INSPECTION_ANGLES`.
- Errors: return HTTP 4xx/5xx with `{ "error": "...", "detail": "..." }`; the
  orchestrator treats any non-2xx as a failed motion.
- Frames: the orchestrator plans grasps in the **base** frame, using the
  camera→base extrinsics it holds (`T_BASE_CAM`). If the arm expects a different
  frame, tell us and we'll transform before calling.
