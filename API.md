# disassemblr — API Reference

HTTP API for the disassemblr VLM-guided robotic-disassembly pipeline. The system
is a set of **containerized FastAPI microservices**, one per pipeline stage, plus
an **orchestrator** that drives the full loop. This document is the practical
wire reference; for the *why* behind each contract see
[`.agent/System/integration_points.md`](.agent/System/integration_points.md) and
the ADRs in [`.agent/Decisions/`](.agent/Decisions/).

## Conventions (read once, applies everywhere)

- **Transport.** JSON over HTTP. Every service exposes interactive OpenAPI docs
  at `GET /docs` and the raw schema at `GET /openapi.json`.
- **Images are base64-in-JSON.** No multipart uploads. Images, depth maps, and
  masks travel as base64-encoded **PNG** strings in JSON fields (e.g.
  `image_b64`, `rgb_b64`, `depth_b64`, `mask_b64`). Depth is **uint16
  millimetres**; masks are single-channel `0/255`.
- **Auth (optional, shared token).** Every *work* endpoint (`POST`s and the SSE
  stream) is gated by a `require_token` dependency checking env `WBK_API_TOKEN`.
  **If `WBK_API_TOKEN` is unset on a service, auth is disabled** (dev / CI /
  mocks need no token). When set, pass it as `Authorization: Bearer <token>`, or
  — for browser `EventSource`, which can't set headers — as `?token=<token>`.
  `GET /health` and `GET /` are always open. This is trusted-LAN anti-spam, not
  real authentication — see [ADR 0009](.agent/Decisions/0009-shared-token-auth.md).
- **Health.** Every service exposes `GET /health` returning at least
  `{"status": "ok", ...}` plus service-specific readiness fields.
- **Ports below are the logical/container ports.** On the deployed GPU server the
  host ports are remapped (perception lands on 6767–6770, reached via SSH tunnel)
  — see [`.agent/SOP/deploy_perception_gpu_server.md`](.agent/SOP/deploy_perception_gpu_server.md).

## Service map

| Stage | Service | Port | Key endpoint(s) |
|---|---|---|---|
| **Orchestrator** (loop driver) | `orchestrator` | `:8000` | `POST /run`, `GET /events/run`, `GET /products`, `GET /plan`, `/slots/*` |
| **Scene camera** (RGB-D capture) | `scene_camera` | `:9002` | `POST /capture` |
| **Perception** (detect / segment / ground) | `yolo` / `yoloseg` / `sam3` / `locateanything` | `:8001`–`:8003` | `POST /infer` |
| **6DoF pose** | `foundationpose` / `gigapose` | `:8004` / `:8005` | `POST /pose` |
| **Damage inspection** | `damage` | (own container) | `POST /inspect` |
| **Robot control** (Jetson bridge) | `robot_control` | `:9000` | `POST /command`, `/robot/execute/`, `/hover/*`, `/calibration/*` |

---

## 1. Orchestrator — `:8000`

The only component that knows the full sequence. Drives every stage in a loop,
in either **fixed mode** (perception-driven) or **plan mode** (ERP + LLM plan).
Registers permissive CORS (`allow_origins=["*"]`) so the browser dashboard can
call it cross-origin.

### `POST /run`
Run one full disassembly loop and return **all events + final stats at once**
(non-streaming). All parameters are query params, all optional:

| Param | Type | Default | Meaning |
|---|---|---|---|
| `dry_run` | bool | `false` | Use mocks instead of real services/hardware — no GPU needed. |
| `target` | `real`\|`sim`\|`both` | env `ROBOT_TARGET` | Which robot to drive; `both` mirrors to the sim digital twin. |
| `product` | string | — | Switch to **plan mode** for this product id (see `GET /products`). Omit → perception-driven fixed loop. |
| `pose_pipeline` | `rgbd`\|`rgb`\|`2d` | env default (`rgbd`) | Override the pose stage; `2d` is the CAD-free planar pose. |
| `localization` | string | env default | Localization mode override. |

**Response:** `{ stats, target, product, pose_pipeline, localization, events[] }`,
where each `events[]` entry is `{ step, state, message, data }` and `state` ∈
`LOCATE, POSE, GRIP, REGRASP, SKIP, REMOVE, RECHECK, SORT, BLOCKED, DONE, SUMMARY`.

Example (dry run, plan mode):
```bash
curl -X POST "http://localhost:8000/run?dry_run=true&product=gearbox-demo"
```

### `GET /events/run` (Server-Sent Events)
Same as `POST /run` but **streams** the loop live — this is what the dashboard
consumes. Query params: `dry_run` (bool), `delay` (seconds to pause after each
event, to pace a watchable demo), `token` (for `EventSource`).

Emits `Content-Type: text/event-stream`. Frame sequence:

| `event:` | When | `data:` |
|---|---|---|
| `start` | immediately | `{"status":"started","dry_run":bool}` |
| `event` | per loop event | `{"step","state","message","data"}` |
| `summary` | run completed | the `stats` dict |
| `error` | run raised | `{"error":"<msg>"}` (named event, not a transport drop) |
| `end` | always last | `{"status":"done"}` — closes the stream |

> **Consumer must close its `EventSource` on `end`/`error`.** Each new connection
> **starts a new run**, so a lingering auto-reconnecting client silently triggers
> extra runs.

### `GET /products`
List operator-selectable products from the (mock) ERP dataset.
**Response:** `{ products: [{ id, name, description, parts[] }] }`.

### `GET /plan?product=<id>&dry_run=<bool>`
Generate — **but do not execute** — the disassembly plan for a product, so the
operator can review the LLM/ERP plan before running.
**Response:** `{ product, source, rationale, steps: [{ index, part, action, notes }] }`.
`404` if the product id is unknown.

### Slots (tray calibration / localization)
- `GET /slots/layout` → the current tray slot layout (pixel centres + base poses).
- `POST /slots/layout` (body: layout dict) → persist an edited layout; returns `{ status, slots, path }`.
- `POST /slots/occupancy` (body: `{ image_b64, mask_source? }`) → score each slot's
  occupancy for one RGB frame; returns per-slot `{ filled, detected_class, fill_score, identity_ok, ... }`. `422` if `image_b64` missing.

### `GET /health`
`{ "status": "ok", "service": "orchestrator" }`.

---

## 2. Scene camera — `:9002`

Captures an RGB-D frame from the fixed eye-to-hand **Zivid** camera (on the
Jetson) in the orchestrator's `SceneFrame` shape. This is the *scene* camera for
perception + pose — **not** the inspection webcam the damage stage uses.

### `POST /capture`
No request body. Returns a captured frame; applies gray-world white balance to
the Zivid RGB when configured (`SCENE_WHITE_BALANCE=grayworld`) to close the
sim-to-real color gap ([ADR 0017](.agent/Decisions/0017-grayworld-white-balance-sim-to-real.md)).

**Response (`SceneCaptureResponse`):**
```jsonc
{
  "rgb_b64":    "<PNG RGB>",
  "depth_b64":  "<PNG uint16-mm>|null",
  "K":          [fx,0,cx, 0,fy,cy, 0,0,1],  // flat-9 row-major, or null
  "width":  1944, "height": 1200,
  "backend": "zivid", "capture_ms": 312.4
}
```

### `GET /health`
`{ status, service, backend, ready }`.

---

## 3. Perception — `:8001`–`:8003`

Four interchangeable detect/segment/ground services sharing one uniform contract
(`perception/services/shared/schemas.py`). Every request extends
`ImageInput { image_b64 }`; every response carries `width, height, model,
inference_ms` plus a service-specific results list. Geometry is model-agnostic:
`BBox{x1,y1,x2,y2}` (pixels, top-left origin), `Point{x,y,label}` (label 1=fg,
0=bg — SAM convention).

### `POST /infer`

| Service | Port | Request extras | Response results |
|---|---|---|---|
| `yolo` | `:8001` | `conf, iou, classes, max_det` | `detections[]` — `{ box, score, class_id, label }` |
| `yoloseg` | (sidecar) | `conf, iou, classes, max_det` | `masks[]` — segmentation instances (`mask_b64_png`, `box`, `score`, `label`) |
| `sam3` | `:8002` | `points, boxes, text, multimask_output` | `masks[]` — `{ mask_b64_png, score, box?, label? }` |
| `locateanything` | `:8003` | `query, top_k, conf` | `locations[]` — `{ point, box?, score, label }` |

Example:
```bash
curl -X POST http://localhost:8001/infer \
  -H 'Content-Type: application/json' \
  -d '{"image_b64":"<PNG b64>","conf":0.10}'
```

> **Masks are `0/255` single-channel PNG.** Producers use the shared
> `encode_mask_png_b64`; consumers threshold at `>127`. (A `{0,1}`-vs-`{0,255}`
> mismatch previously made `yoloseg` masks read as empty — fixed 2026-07-08.)

### `GET /health`
`{ status, service, model, device, loaded }`. Also `GET /` (info), `GET /docs`.

> **Note (SAM3):** prompts must be **English text**; weights (`facebook/sam3`)
> are gated on HuggingFace and require `hf auth login` / `HF_TOKEN` before first load.

---

## 4. 6DoF pose — `:8004` / `:8005`

One contract shared verbatim by `foundationpose` (`:8004`) and `gigapose`
(`:8005`), defined in `pose/shared/schemas.py`. The `/pose` wire shape is
deliberately identical to the KIP `kip-pose-viewer` reference so estimators are
interchangeable ([ADR 0004](.agent/Decisions/0004-pose-contract-reuses-kip-pose-viewer.md)).

### `POST /pose`
**Request (`PoseRequest`):**
```jsonc
{
  "rgb_b64":   "<PNG uint8 RGB>",
  "depth_b64": "<PNG uint16 MILLIMETRES>",   // required: foundationpose; optional: gigapose
  "K":         [fx,0,cx, 0,fy,cy, 0,0,1],    // flat-9 row-major intrinsics
  "instances": [{ "id": 0, "class": "housing", "mask_b64": "<PNG 0/255>" }],
  "iterations": 5,
  // gigapose-only (ignored by foundationpose):
  "hypotheses": 5, "pipeline": "rgbd", "kabsch": true,
  "plane_z": null                            // pipeline='2d' only: table depth (m)
}
```
**Response (`PoseResponse`):**
```jsonc
{ "poses": [{ "id", "class", "T_cam_obj": [[4x4]], "score?", "stage?" }],
  "timings": { "pose_ms", "num_posed" } }
```
`T_cam_obj` is a 4×4 row-major **object→camera** transform in the **OpenCV camera
frame** (x right, y down, +z forward), in **metres**. `score`/`stage` are
GigaPose-only (FoundationPose leaves both null).

- **`pipeline`** (GigaPose): `rgbd` (default) / `rgb` / **`2d`** — the CAD-free,
  model-free planar pose used when no CAD templates exist for the parts
  ([ADR 0016](.agent/Decisions/0016-gigapose-2d-planar-pose-mode.md)). A
  `rgb`/`rgbd` request to an instance whose 6DoF model didn't load returns a
  clear `503`.
- Depth must be **metric uint16 mm** exactly; FoundationPose is ~2 s/instance and
  serial — cap the instance count from the caller.

### `GET /health`
`{ status, service, model, device, loaded, classes }` — `classes: []` means the
instance has no CAD templates (2D pipeline only).

---

## 5. Damage inspection — `POST /inspect`

VLM-based OK/not-OK quality gate on removed parts (`damage/schemas.py`).

**Request (`DamageRequest`):**
```jsonc
{
  "images_b64": ["<PNG>", ...],          // required, >=1, multi-angle shots
  "part_class": "gearbox_housing",       // optional: loads disk reference + labels prompt
  "reference_ok_b64": "<PNG>",           // optional inline references
  "reference_damaged_b64": "<PNG>",
  "notes": "check the mating flange for hairline cracks"   // optional guidance
}
```
**Response (`DamageVerdict`):**
```jsonc
{
  "verdict": "ok" | "damaged" | "uncertain",
  "damaged": false,
  "confidence": 0.92,
  "bin": "ok_bin" | "reject_bin",
  "issues": ["..."], "reasoning": "...", "model": "...", "part_class": "..."
}
```
> **`bin` is decided server-side, fail-closed** — only a clean `ok` → `ok_bin`;
> both `damaged` **and** `uncertain` → `reject_bin`. The VLM does not choose the
> bin ([ADR 0003](.agent/Decisions/0003-damage-failsafe-sort-policy.md)).

### `GET /health`
`{ status, service, model, api_key_present, reference_dir }`.

---

## 6. Robot control (Jetson bridge) — `:9000`

Group 2's bridge to the LARA5/NEURA arm's socket server. Movement stage of the
pipeline; hover-planning gates enforce safety before motion.

| Endpoint | Purpose |
|---|---|
| `POST /command` | Send a raw `RobotCommand`. |
| `POST /robot/execute/` | Execute a robot command → `RobotCommandResponse`. |
| `WS /ws/joint_states` | WebSocket stream of live joint states. |
| `GET /probe` | Probe robot connectivity. |
| `POST /raw` | Send a raw low-level command. |
| `POST /hover/plan` · `POST /hover/execute` | Plan / execute a safety-gated hover-then-approach move. |
| `GET /calibration` · `POST /calibration/points` · `POST /calibration/solve` | Hand-eye calibration workflow. |
| `GET /health` | Liveness (auth-free; routes are token-gated when set). |

Full detail and safety semantics: [`.agent/System/robot_control.md`](.agent/System/robot_control.md).

---

## Errors

- Services return standard HTTP status codes; failures surface as JSON
  `{ "error": <type>, "detail": <str> }` with a `500` (or `422` for validation,
  `404` for unknown ids, `503` for a not-ready model).
- **CORS on errors:** top-level exception handlers explicitly re-add
  `Access-Control-Allow-Origin: *`, since Starlette's outermost error middleware
  sits above the CORS middleware — without it, browser callers saw every 500 as
  an opaque "network error" ([ADR 0017](.agent/Decisions/0017-grayworld-white-balance-sim-to-real.md)).

---

*Contracts and schemas live in each service's `schemas.py`. A breaking change
here also breaks the orchestrator's HTTP clients (`orchestrator/clients/`). See
[`.agent/System/integration_points.md`](.agent/System/integration_points.md)
before modifying any wire contract.*
