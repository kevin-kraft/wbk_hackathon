# Contract — scene-camera (Zivid) capture endpoint

The scene RGB-D camera for perception + 6DoF pose. Implemented in `scene_camera/`
and consumed by the orchestrator's `HttpSceneCamera` (satisfies the `SceneCamera`
protocol). Base URL via `SCENE_CAMERA_URL` (e.g. `http://172.22.192.166:9002`,
the Jetson). Not the inspection webcam (that's the damage stage).

## `POST /capture`
Capture one RGB-D frame. No body required.

```jsonc
// response — a superset of the orchestrator's SceneFrame
{
  "rgb_b64": "<base64 PNG>",     // stored BGR; pose decodes IMREAD_COLOR then BGR->RGB
  "depth_b64": "<base64 PNG>",   // 16-bit single-channel, millimetres; pose does UNCHANGED then /1000 -> metres. 0 = no return. null if unavailable
  "K": [fx, 0, cx, 0, fy, cy, 0, 0, 1],  // flat-9 row-major intrinsics, or null
  "width": 1944,
  "height": 1200,
  "backend": "zivid",
  "capture_ms": 312.4
}
```

The orchestrator forwards `rgb_b64` / `depth_b64` / `K` unchanged to the
perception (`/infer`) and pose (`/pose`) stages, so the encodings above must
stay byte-compatible with `pose/shared/imaging.py`.

## `GET /health`
```jsonc
{ "status": "ok", "service": "scene_camera", "backend": "zivid", "ready": true }
```
`ready` reflects whether the camera is connectable. `/health` is exempt from the
shared token; `/capture` requires it when `WBK_API_TOKEN` is set (`Authorization:
Bearer <token>` or `?token=`).

## Notes
- Depth and XYZ from the Zivid are in **mm**; the pose stack is in **metres** —
  the ÷1000 happens on decode, so keep depth in mm on the wire.
- Intrinsics come from the Zivid SDK; if that read is unavailable, pin them with
  the service's `SCENE_K` env (or the orchestrator's `SCENE_K`).
- Errors: non-2xx with `{ "error": "...", "detail": "..." }`.
