# Integration Points & Wire Contracts

## Related Docs
- [Architecture](./architecture.md) — pipeline overview and per-stage service map
- [System: Orchestrator](./orchestrator.md) — the orchestrator's `HttpPerception`/`HttpPose`/`HttpDamage` clients are consumers of the three contracts below; also owns the `/events/run` SSE producer described here
- [System: Dashboard](./dashboard.md) — the SSE contract's consumer (`useRunStream`)
- [ADR: pose contract reuses kip-pose-viewer](../Decisions/0004-pose-contract-reuses-kip-pose-viewer.md)
- [ADR: dashboard is a separate static app](../Decisions/0008-frontend-separate-static-app.md) — why SSE + CORS exist at all
- [ADR: shared-token auth](../Decisions/0009-shared-token-auth.md) — why every `POST` contract below is gated, the threat model, and its limits
- [ADR 0016: GigaPose 2D (planar) pose mode](../Decisions/0016-gigapose-2d-planar-pose-mode.md) — the `pipeline='2d'` addition to Contract 2
- [SOP: deploying the pose services (podman)](../SOP/deploy_pose_podman.md) — required auth on the deployed pose services (stricter than perception's), the no-CAD-templates reality behind `pipeline='2d'`
- [SOP: running the services](../SOP/running_services.md)

This doc covers the things a change to *any* stage is likely to touch: the
wire contracts between stages, the shared model-adapter pattern, and the
model-weight cache mount. Read this before modifying `schemas.py` in any
stage, or before adding a new perception/pose backend — a breaking change
here also breaks the orchestrator's HTTP clients
(`orchestrator/clients/http_perception.py`, `http_pose.py`, `http_damage.py`).

## Design conventions shared across all three stages

- **Base64-in-JSON everywhere.** No multipart uploads. Every request that
  carries an image encodes it as a base64 string (PNG for images/depth/masks).
  This keeps service-to-service calls trivial (a `curl`+`jq` one-liner, no
  multipart boilerplate) at the cost of ~33% payload bloat over raw bytes —
  acceptable for a hackathon-scale pipeline.
- **Thin web layer, fat adapter.** Every service is `app.py` (routing only) +
  `model.py` (a `*Runner`/`*Backend` class that owns weight loading and
  inference). Swapping a backend model means editing one file
  (`model.py`); `app.py` never changes.
- **Load once at startup, GPU-resident.** Every FastAPI app uses a lifespan
  context manager that calls `model.load()` before serving traffic, and
  `model.unload()` on shutdown. No per-request model loads.
- **Independently containerizable.** Every service directory is self-contained
  (own `model.py`, `app.py`/`main.py`, `requirements.txt`) so it can be
  extracted into its own container without touching siblings.
- **Optional shared-token auth on the work endpoint.** Every `POST /infer` /
  `/pose` / `/inspect` route (plus the orchestrator's `/run` and
  `/events/run`, contract 4 below) carries `dependencies=[Depends(require_token)]`
  — a `require_token` FastAPI dependency copy-pasted into each package
  (`perception/services/shared/auth.py`, `pose/shared/auth.py`,
  `damage/auth.py`, `orchestrator/auth.py`, identical logic). It checks the
  request against env `WBK_API_TOKEN`; **unset = disabled**, so
  dev/CI/mocks/dry-run need no token. `GET /health` (and `/`) are always
  open. See [ADR 0009](../Decisions/0009-shared-token-auth.md) for the
  design and its trusted-LAN-only threat model.

## Contract 1 — Perception `POST /infer`

Base path differs per service but the shape is uniform: a request that always
extends `ImageInput` (`image_b64: str`), a response that always carries
`width`, `height`, `model`, `inference_ms` plus a service-specific results list.
Defined in `perception/services/shared/schemas.py`.

| Service | Request extra fields | Response results field |
|---|---|---|
| yolo (`:8001`) | `conf`, `iou`, `classes`, `max_det` | `detections: list[Detection]` (`box`, `score`, `class_id`, `label`) |
| sam3 (`:8002`) | `points`, `boxes`, `text`, `multimask_output` | `masks: list[MaskResult]` (`mask_b64_png`, `score`, `box?`, `label?`) |
| locateanything (`:8003`) | `query`, `top_k`, `conf` | `locations: list[Location]` (`point`, `box?`, `score`, `label`) |

Shared geometry: `BBox{x1,y1,x2,y2}` (pixel, top-left origin), `Point{x,y,label}`
(`label`: 1=foreground/positive, 0=background/negative — SAM prompt convention).
These are intentionally model-agnostic: a YOLO detection and a LocateAnything
hit both surface as a box/point/score, so a downstream consumer (grasp
planning, when it exists) does not need to branch on which model produced it.

Every perception service also exposes `GET /health` → `HealthResponse{status,
service, model, device, loaded}` and `GET /` (info) and `GET /docs` (OpenAPI).

**Mask encoding gotcha, fixed 2026-07-08 (commit `4b6d1d3`):** every mask a
service returns (`sam3`'s `MaskResult`, `yoloseg`'s `SegInstance`) is a
single-channel PNG via the shared `encode_mask_png_b64`
(`perception/services/shared/imaging.py`), and every consumer (frontend
overlay, `gigapose`'s `pipeline='2d'`) thresholds it at `> 127`, assuming
0/255. The helper used to skip its binarization step for any already-`uint8`
input — but Ultralytics `result.masks.data` is uint8 valued `{0,1}`, so
`yoloseg` masks went out at `{0,1}` and read back as **empty** everywhere.
Fixed to always binarize (`(mask > 0) * 255`, idempotent for already-0/255
inputs) — see [System: Architecture](./architecture.md) for the full
incident writeup. If you add a new mask-producing service, use
`encode_mask_png_b64` rather than a bespoke encoder, or you'll need to
re-derive this fix independently.

`POST /infer` requires `WBK_API_TOKEN` (`Authorization: Bearer <token>`) when
that env var is set on the service — see [ADR 0009](../Decisions/0009-shared-token-auth.md).
`GET /health`/`/`/`/docs` stay open regardless.

## Contract 2 — Pose `POST /pose`

One contract, shared verbatim by both `foundationpose` (`:8004`) and
`gigapose` (`:8005`) services — defined once in `pose/shared/schemas.py`.

Request (`PoseRequest`):
```jsonc
{
  "rgb_b64":   "<PNG uint8 RGB>",
  "depth_b64": "<PNG uint16 MILLIMETRES>",   // required for foundationpose, optional for gigapose
  "K":         [fx,0,cx, 0,fy,cy, 0,0,1],    // flat 9, row-major
  "instances": [{"id": 0, "class": "housing", "mask_b64": "<PNG 0/255>"}],
  "iterations": 5,
  // gigapose-only knobs (ignored by foundationpose):
  "hypotheses": 5, "pipeline": "rgbd", "kabsch": true,
  // gigapose pipeline='2d' only — camera-frame table depth (metres), used
  // when a per-mask depth value is unavailable; omit to fall back further
  // to a built-in default:
  "plane_z": null
}
```
Response (`PoseResponse`): `{"poses": [{"id","class","T_cam_obj":[[4x4]],
"score?","stage?"}], "timings": {"pose_ms","num_posed"}}`.

`T_cam_obj` is always a 4x4 row-major object→camera transform, **OpenCV camera
frame** (x right, y down, +z forward), in **metres**. `score` is populated by
GigaPose only; `stage` (`'coarse'|'refined'|'refined+kabsch'` for
`rgb`/`rgbd`, or `'2d'|'2d-plane'|'2d-defaultz'` for `pipeline='2d'`) is
GigaPose-only too — FoundationPose leaves both `null`.

**`pipeline='2d'` (GigaPose only, added 2026-07-08)**: a CAD-free,
model-free planar pose, added because the deployed `wbk-gigapose` has no CAD
templates for this project's parts (`GET /health`'s `classes: []`) — see
[System: Architecture](./architecture.md) "GigaPose `pipeline='2d'`" and
[ADR 0016](../Decisions/0016-gigapose-2d-planar-pose-mode.md). It bypasses
`GigaPoseRunner` entirely (`pose/shared/planar.py`'s `planar_pose()`,
numpy-only) and returns the same `ObjectPose` shape — a client cannot tell
from the response shape alone which pipeline produced a pose; check `stage`.
A `pipeline='rgb'`/`'rgbd'` request against a GigaPose instance whose 6DoF
model failed to load (or was never asset-ready) now gets a clear `503`
instead of the service failing to start at all — see the same ADR for the
graceful-degrade change in `gigapose_svc/app.py`'s startup lifespan.

`GET /health` → `PoseHealth{status, service, model, device, loaded, classes}`.

`POST /pose` requires `WBK_API_TOKEN` when set on the service (same
`require_token` dependency as perception) — see
[ADR 0009](../Decisions/0009-shared-token-auth.md). `GET /health` stays
open.

Fragile bits carried over from the KIP reference (see `pose/README.md`):
depth must be **metric uint16 mm** exactly (GigaPose does subtle mm↔m handling
internally); GigaPose needs 162 pre-rendered templates per object on disk
*before* the service starts, correctly scaled, or coarse matching silently
degrades; FoundationPose is ~2s/instance and serial (non-thread-safe shared GL
context) — cap instance count via the caller.

## Contract 3 — Damage `POST /inspect`

Defined in `damage/schemas.py`.

Request (`DamageRequest`): `images_b64` (required, ≥1, multi-angle shots of the
target part), optional `part_class` (triggers disk-backed reference loading +
labels the prompt), optional inline `reference_ok_b64`/`reference_damaged_b64`,
optional `notes` (free-text inspection guidance, e.g. "check the mating flange
for hairline cracks").

Response (`DamageVerdict`): `verdict` (`"ok"|"damaged"|"uncertain"`),
`damaged: bool`, `confidence: float`, `bin` (`"ok_bin"|"reject_bin"`),
`issues: list[str]`, `reasoning: str`, `model`, `part_class?`.

`bin` is derived server-side in `damage/app.py`, not by the VLM — see
[ADR 0003](../Decisions/0003-damage-failsafe-sort-policy.md) for the policy
and why it lives there instead of trusting the model's own bin choice.

`GET /health` → `DamageHealth{status, service, model, api_key_present,
reference_dir}`.

`POST /inspect` requires `WBK_API_TOKEN` when set on the service (same
`require_token` dependency as the other two stages) — see
[ADR 0009](../Decisions/0009-shared-token-auth.md). `GET /health` stays
open.

## Contract 4 — Orchestrator live loop `GET /events/run` (SSE)

Defined in `orchestrator/app.py`. This is the one contract in the repo that
isn't request/response — it's a **Server-Sent Events** stream, added so the
[dashboard](./dashboard.md) can narrate a run live instead of waiting for
`POST /run` to finish and return one batch. See
[ADR 0008](../Decisions/0008-frontend-separate-static-app.md) for why this
exists as a separate app's needs rather than folded into `POST /run`.

Request: `GET /events/run?dry_run=<bool>&delay=<seconds>` — `dry_run`
(default `false`) picks mocks vs. real clients exactly like `POST /run`;
`delay` (default `0.0`) sleeps that many seconds after each emitted event, in
the server-side worker thread, to pace the stream for a watchable demo
(mocks otherwise finish in milliseconds).

Both `POST /run` and `GET /events/run` require `WBK_API_TOKEN` when set (see
[ADR 0009](../Decisions/0009-shared-token-auth.md)). `GET /events/run` is
the reason the token transport has a query-param form at all:
`?token=<token>` alongside `dry_run`/`delay`, because a browser
`EventSource` (the dashboard's SSE client) cannot set an `Authorization`
header — `POST /run` also accepts the query form but normally uses the
header instead.

Response: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`Connection: keep-alive`, `X-Accel-Buffering: no` (disables proxy buffering
so events aren't batched). Frame sequence, one `event: <name>\ndata:
<json>\n\n` block per frame:

| `event:` name | When | `data:` payload |
|---|---|---|
| `start` | once, immediately | `{"status": "started", "dry_run": bool}` |
| `event` | once per `LoopEvent` the loop emits | `{"step", "state", "message", "data"}` — same shape as `POST /run`'s `events[]` entries; `state` is one of `LOCATE, POSE, GRIP, REGRASP, SKIP, REMOVE, RECHECK, SORT, BLOCKED, DONE, SUMMARY` (see [System: Orchestrator](./orchestrator.md)) |
| `summary` | once, run completed normally | the `stats` dict (`removed`, `ok_bin`, `reject_bin`, `skipped`, ...) |
| `error` | once, only if the run raised | `{"error": "<str(exc)>"}` — a **named** SSE event, distinct from a transport-level connection drop |
| `end` | always, last frame | `{"status": "done"}` — closes the stream |

Consumer contract: a client **must** close its `EventSource` on `end` (or on
the named `error` event). `EventSource` auto-reconnects by default, and every
new connection to `GET /events/run` **starts a new loop run** — not closing
on `end` would silently trigger a second run. The dashboard's
`useRunStream.ts` does this; see [System: Dashboard](./dashboard.md).

**CORS**: `app.py` registers `CORSMiddleware` with `allow_origins=["*"]`,
`allow_credentials=False`, all methods/headers allowed — needed because the
dashboard is served from a different origin than the orchestrator (see
[ADR 0008](../Decisions/0008-frontend-separate-static-app.md)). This applies
to the whole orchestrator app, not just `/events/run` — `POST /run` and `GET
/health` are cross-origin-callable too.

## The model-adapter pattern (perception)

Every perception backend subclasses `BasePerceptionModel`
(`perception/services/shared/model_base.py`):

```python
class BasePerceptionModel(abc.ABC):
    name: str = "base"
    def __init__(self, settings: Settings): ...
    @abc.abstractmethod
    def load(self) -> None: ...   # must set self._loaded = True
    def unload(self) -> None: ...
```

`perception/services/shared/app_factory.py`'s `create_service_app(service_name,
model)` wraps this into a FastAPI app: a lifespan hook that calls
`model.load()` at startup / `model.unload()` at shutdown, plus `/health`, `/`,
and a catch-all exception handler that returns `{"error": type, "detail": str}`
with a 500. Each service then adds its own typed `/infer` route in `main.py`.

To add a new perception model: subclass `BasePerceptionModel` in
`services/<name>/model.py` (implement `load()`/`infer()`), add
`services/<name>/main.py` using `create_service_app(...)`, add request/response
types to `shared/schemas.py`, and register a `[program:<name>]` block in
`supervisord.conf` plus a port in the Dockerfile/compose. (From
`perception/README.md`, "Adding a model / service".)

Pose services follow the same thin-app/fat-adapter split but do **not** share
a common base class across `FoundationPoseRunner`/`GigaPoseRunner` the way
perception does — they only share the wire-contract schemas and imaging
helpers in `pose/shared/`. This is consistent with them living in separate
containers with incompatible dependency stacks (nothing forces a shared Python
base class across container boundaries).

## HF weight cache mount

`docker-compose.yml`'s `perception` service mounts a named volume at
`/root/.cache/huggingface` (`hf-cache:/root/.cache/huggingface`) plus a bind
mount `./weights:/weights` (env `WEIGHTS_DIR=/weights`). This is what lets
`transformers`/`AutoModel.from_pretrained(...)` calls (SAM 3, LocateAnything)
reuse downloaded weights across container rebuilds instead of re-pulling
multi-GB checkpoints every `docker compose up --build`. SAM 3's weights
(`facebook/sam3`) are **gated on HuggingFace** — `hf auth login` (or set
`HF_TOKEN`) is required before the first successful load. See
[SOP: running the services](../SOP/running_services.md) for the exact
one-time setup steps.

The `pose/` containers do **not** use the HF cache — FoundationPose and
GigaPose load meshes/templates from bind-mounted directories
(`./pose/assets/meshes`, and the mounted model-repo working trees themselves),
not from HuggingFace.

## Deferred imports (why the test suite can mock everything)

Every adapter's heavy ML imports (`torch`, `transformers`, `ultralytics`,
`nvdiffrast`, the FoundationPose/GigaPose repo modules) are imported **inside**
`load()`/`infer()`/`estimate()`, never at module top-level. This is what lets
`tests/` exercise schemas, imaging helpers, and FastAPI route wiring (with the
adapter instance monkeypatched) without ever installing torch or having a GPU.
See [SOP: running the tests](../SOP/running_tests.md).
