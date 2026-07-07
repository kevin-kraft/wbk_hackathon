# Scene camera (Zivid) capture service

Captures an **RGB-D frame from the Zivid** — the fixed, eye-to-hand *scene*
camera looking at the assembly — and returns it in the orchestrator's
`SceneFrame` shape. This is the camera for **perception + 6DoF pose**, *not* the
inspection webcam the damage VLM uses (that stays `OpenCVInspectionCamera`).

Runs on the **Jetson**, where the Zivid is connected (USB3/GigE). Fills the
`SceneCamera` seam via `orchestrator/clients/http_scene.py` (`HttpSceneCamera`),
selected when `SCENE_CAMERA_URL` is set.

## Endpoints

```text
GET  /health   -> {status, backend, ready}
POST /capture  -> SceneFrame {rgb_b64, depth_b64, K, width, height, backend, capture_ms}
```

- `rgb_b64` — PNG (stored BGR; the pose stage decodes BGR→RGB).
- `depth_b64` — **16-bit mm PNG** (pose decodes `UNCHANGED` then ÷1000 → metres);
  no-return pixels (Zivid NaN) are stored as 0.
- `K` — flat-9 row-major intrinsics. From the Zivid SDK, or pin with `SCENE_K`.

## Config (env)

| var | default | meaning |
|---|---|---|
| `SCENE_CAMERA_BACKEND` | `zivid` | `zivid` \| `mock` \| `file` |
| `ZIVID_SETTINGS_PATH` | — | Zivid Studio settings YAML (else a default single-acquisition capture) |
| `SCENE_K` | — | flat-9 intrinsics override (JSON), if the SDK read is unavailable |
| `SCENE_DEPTH_MAX_MM` | `65535` | clamp for the 16-bit depth PNG |
| `SCENE_RGB_PATH` / `SCENE_DEPTH_PATH` | — | inputs for the `file` backend (dev) |
| `WBK_API_TOKEN` | — | shared token; `/health` exempt. Unset = auth off |

## Run

Dev (no camera): `SCENE_CAMERA_BACKEND=mock uvicorn scene_camera.app:app --port 9002`

On the Jetson (real): install the Zivid SDK + `pip install zivid`, connect the
camera, then run natively in that venv (simplest for USB HW) or via Docker with
the USB device passed through. `SCENE_CAMERA_BACKEND=zivid` is the default.

## Wiring

The orchestrator captures the scene, then forwards `rgb_b64`/`depth_b64`/`K` to
perception and pose. Point it at this service with `SCENE_CAMERA_URL`
(e.g. `http://172.22.192.166:9002`, the Jetson). Contract:
[`contracts/scene_camera_api.md`](../contracts/scene_camera_api.md).
