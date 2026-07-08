# Dashboard (`frontend/`) — operator console + live demo UI

## Related Docs
- [Architecture](./architecture.md) — full pipeline overview, per-stage service map
- [System: Orchestrator](./orchestrator.md) — the `GET /events/run` SSE endpoint this app consumes, and `LoopEvent`/loop-state shapes it mirrors
- [Integration Points & Wire Contracts](./integration_points.md) — the SSE event contract + CORS
- [ADR 0008: dashboard is a separate static app](../Decisions/0008-frontend-separate-static-app.md) — why this isn't fused into the orchestrator
- [ADR 0009: shared-token auth](../Decisions/0009-shared-token-auth.md) — the `apiToken` field below, and why `GET /events/run` needed a query-param token transport
- [ADR 0011: LLM action selector, constrained vocabulary](../Decisions/0011-llm-action-selector-constrained-vocabulary.md) — the `GUARDRAIL` event `PlanProgress`/the event log surface
- [ADR 0014: robot target selection (real \| sim \| both)](../Decisions/0014-robot-target-real-sim-both.md) — the Real/Sim/Both toggle this doc's "Sim / digital-twin UI" section covers
- [ADR 0015: YOLO-Seg sidecar container, no rebuild](../Decisions/0015-yoloseg-sidecar-container-no-rebuild.md) — the deployment behind the `yoloseg` service this doc's Perception page section calls
- [ADR 0016: GigaPose 2D (planar) pose mode](../Decisions/0016-gigapose-2d-planar-pose-mode.md) — the pose pipeline the "Pose pipeline selector" section below picks between
- [ADR 0017: gray-world white balance + lowered detection confidence](../Decisions/0017-grayworld-white-balance-sim-to-real.md) — the frontend-side default-conf and SAM3/LocateAnything prompt changes this doc's Perception page section reflects
- `contracts/simulation_api.md` / `contracts/sim_scene_capture.md` — the Isaac Sim command-bus + (draft, unimplemented) scene-capture surfaces the sim-side UI calls
- `frontend/README.md` (in-repo) — the module's own README; this doc adds the `.agent/` cross-reference layer on top, not a duplicate

## What it is

`frontend/` (`wbk-disassembly-dashboard`, added alongside the orchestrator SSE
change) is a **separate static single-page app** — React 19 + Vite 6 +
TypeScript + Tailwind v4 (via `@tailwindcss/vite`) — that is the operator
console and live demo UI for the disassembly pipeline. It is a pure HTTP/SSE
client of the orchestrator and the other stage services; it holds no server
state of its own. See [ADR 0008](../Decisions/0008-frontend-separate-static-app.md)
for why it's a standalone app rather than served by the orchestrator.

Routing is `HashRouter` (`frontend/src/App.tsx`) — deliberate for a static
SPA served by plain nginx with no server-side rewrite guarantees; deep links
resolve entirely client-side (`nginx.conf`'s `try_files` fallback is
belt-and-braces on top of that, not the primary mechanism).

`npm run build` runs `tsc -b && vite build` (type-check + bundle to `dist/`)
and is verified clean.

`npm test` runs a **Vitest** unit suite (30 tests, jsdom env,
`frontend/vitest.config.ts`, `src/**/*.test.ts`) — see "Test suite" below.

## The four pages (`frontend/src/pages/`)

| Page | File | What it shows |
|---|---|---|
| Dashboard | `DashboardPage.tsx` | Run controls (start/stop, dry-run toggle, pace/delay, the Real/Sim/Both robot-target toggle, the 6DoF/6DoF·RGB/2D pose-pipeline toggle — added 2026-07-08, see "Pose pipeline selector" below, `ProductSelector` — see "Plan mode UI" below), the 7-stage pipeline tracker (`StageTracker`) driven by the *latest* live event, `PlanProgress` (plan-driven runs only), scene camera (real `MjpegView` or, in Sim source mode, a rendered preview — see "Sim / digital-twin UI" below), grip telemetry, a next-part text prompt box, bin tallies, and the full event log. |
| Perception | `PerceptionPage.tsx` | **Rewritten 2026-07-08** — no longer a stub: capture a scene (real Zivid or sim render, via `SourceToggle`) or **upload a local image** (debug aid, added 2026-07-08 — see "YOLO-Seg + manual image upload" below), pick a target part (`PartSelector`) or a custom prompt, run YOLO-Det / YOLO-Seg / SAM 3 / LocateAnything inference, and see the result rendered as box/mask/point overlays on the captured frame (`SceneView`) — see "Sim / digital-twin UI" and "YOLO-Seg + manual image upload" below. Detection overlays are no longer future work. |
| Inspection | `InspectionPage.tsx` | Inspection camera, the damage-VLM endpoint, a per-part OK/damaged verdicts table, and bin state. |
| Settings | `SettingsPage.tsx` | Live-editable text fields for every service endpoint (now including the simulator's `movementSim`/`gripSim` and the Zivid `sceneCapture` service) and both camera stream URLs, plus run defaults (dry-run, pace, the default robot target, and — added 2026-07-08, see "Pose pipeline selector" below — the default pose pipeline) and the shared `apiToken` (see "Auth token" below); "Save & reload" persists to `localStorage`, "Reset to config.json" clears the override. |

Shared building blocks in `frontend/src/components/`: `Layout`, `StageTracker`
(maps loop state → one of the 7 canonical stages, see `lib/stages.ts`),
`EventLog`, `GripTelemetry`, `BinTally`, `PromptBox`, `MjpegView` (raw
`<img>`-based MJPEG viewer), `ServiceHealthStrip`, `ServiceInfo`, `ui.tsx`
(`Card`, etc.) primitives; `ProductSelector` and `PlanProgress` (added
2026-07-08, see "Plan mode UI" below); and `SourceToggle`, `PartSelector`,
`SceneView` (added 2026-07-08, see "Sim / digital-twin UI" below).

## Plan mode UI (`ProductSelector`, `PlanProgress`, added 2026-07-08)

Mirrors the orchestrator's plan-driven `run(product=...)` mode (see
[System: Orchestrator](./orchestrator.md) "Plan mode"):

- **`ProductSelector`** (`frontend/src/components/ProductSelector.tsx`) —
  a dropdown fetched from `GET /products` (`fetchProducts()` in
  `lib/api.ts`), plumbed into `RunControls` via a `productSlot` prop.
  `value=""` means manual/fixed mode; selecting a product threads that ID
  through to `runOnce()`/`runStreamUrl()` as the `product` query param
  (`lib/api.ts`, `useRunStream.start()`, `runContext.tsx`).
- **`PlanProgress`** (`frontend/src/components/PlanProgress.tsx`) — a live
  checklist of the generated plan, rendered only when a `PLAN_GENERATED`
  event has arrived (returns `null` otherwise — invisible in fixed-mode
  runs). Driven by `derivePlan(events)` (`lib/derive.ts`): the
  `PLAN_GENERATED` event supplies the full step list (`part`, `action`);
  subsequent `STEP` events mark a row `active` by index, `SORT` marks the
  active row `done`, `SKIP` marks it `skipped`, `BLOCKED` marks it `blocked`.
  Shows the plan's `source` (`static` | `llm` | `mock` | `static-fallback`)
  above the checklist.

## Sim / digital-twin UI (added 2026-07-08)

Mirrors the orchestrator's `ROBOT_TARGET`/`?target=` robot selection (see
[System: Orchestrator](./orchestrator.md) "Robot target selection" and
[ADR 0014](../Decisions/0014-robot-target-real-sim-both.md)) and lets an
operator drive/inspect the Isaac Sim digital twin from the browser:

- **Robot-target toggle** (`RunControls.tsx`) — Real / Sim / Both buttons,
  disabled while a run is in progress or while *Dry run* is checked (mocks
  ignore the target). Sim/Both are additionally disabled until a simulator
  endpoint is configured (`simAvailable = Boolean(serviceUrl("movementSim"))`
  in `DashboardPage.tsx`). `onStart` passes `dryRun ? undefined :
  robotTarget` through to `useRunStream.start()` → `runStreamUrl()`'s
  `?target=` param (see [System: Orchestrator](./orchestrator.md) "Entry
  points"). The server's actually-used target comes back on the SSE `start`
  frame and is surfaced via `RunStreamState.activeTarget`
  (`useRunStream.ts`) — rendered as a "▶ REAL ARM" / "▶ SIMULATOR" /
  "▶ REAL + SIM" badge next to the run-status pill, in case `ROBOT_TARGET`
  was forced server-side and differs from what was requested.
- **`SIM_WARN`** (`lib/types.ts` `LoopState`, `lib/stages.ts` `STATE_STYLE`)
  — the event log renders a `both`-mode mirror-fault event (raised by
  `TeeMovement`, see [ADR 0014](../Decisions/0014-robot-target-real-sim-both.md))
  with the same amber "attention" pill as `GUARDRAIL`/`REGRASP`/`BLOCKED` —
  a warning, not a run failure; the run keeps going.
- **`SourceToggle`** (`frontend/src/components/SourceToggle.tsx`) — Real /
  Sim picker for **scene images only** (independent of the robot target —
  an operator can watch a Sim-rendered scene while still driving the real
  arm, or vice versa). Lifted to `RunProvider`'s `sourceMode`/`setSourceMode`
  (`runContext.tsx`), defaulting to `sim` when the initial robot target is
  `sim`, else `real`. Used on the Dashboard (scene preview) and Perception
  page (capture source).
- **`captureScene(mode)`** (`lib/api.ts`) — real mode `POST`s the Zivid
  `scene_camera` service's `/capture` (`serviceUrl("sceneCapture")`); sim
  mode `POST`s the Isaac backend's `/simulation/scene/capture`
  (`serviceUrl("movementSim")` + the path from `contracts/sim_scene_capture.md`).
  A `404`/`501` response (the contract's documented "not implemented yet"
  status) is normalized to the exported `SIM_NOT_IMPLEMENTED` sentinel error,
  which `PerceptionPage.tsx`/`DashboardPage.tsx`'s `friendlyError()` helpers
  turn into "Sim scene capture isn't implemented yet (Group 2). Switch to
  Real, or see contracts/sim_scene_capture.md." — a UI-level degrade-
  gracefully path for a contract Group 2 hasn't built yet, not an error state.
  `generateScenePreview()` (Dashboard's frontal overview render) follows the
  same `SIM_NOT_IMPLEMENTED` pattern against `/simulation/scene/preview`.
- **`PerceptionPage.tsx`, rewritten** — was a static `MjpegView` stub with a
  "detection overlays: future" note; now a working capture→infer→overlay
  loop: *Capture Zivid view* (or *Render Zivid view* in Sim source mode) →
  pick YOLO / SAM 3 / LocateAnything → for SAM 3/LocateAnything, pick a
  target part via `PartSelector` or a free-text prompt → `runYolo()`/
  `runSam3()`/`runLocate()` (`lib/api.ts`'s `postInfer()` helper, `POST
  {service}/infer`) → results rendered on `SceneView` as YOLO boxes, SAM 3
  masks (toggleable boxes/masks view), or LocateAnything box+point overlays.
- **`PartSelector`** (`frontend/src/components/PartSelector.tsx`) +
  `lib/parts.ts`'s `SUPPORTED_PARTS` — a fixed three-part vocabulary (`anker`,
  `bürstenhalter`/brush holder, `poltopf`) for the open-vocab SAM 3/
  LocateAnything prompt, **the "short" (`kurz`) variant of each part only**
  (operator decision, 2026-07-07), plus a "Custom…" free-text escape hatch.
  Does not apply to YOLO, which has a fixed closed (COCO-80, now custom-
  trained 18-class, see [System: Training](./training.md)) vocabulary with no
  prompt. **`anker`'s actual prompt string, fixed 2026-07-08 (commit
  `fcc2773`):** `SUPPORTED_PARTS`'s `id` is still `"anker"` (label still
  "Anker"), but the `prompt` sent to SAM 3/LocateAnything is now `"copper
  part"` — the German part name `"anker"` didn't match either open-vocab
  model's training distribution (0 masks); the English open-vocab concept
  does (12 masks, verified against a real frame) — see [ADR
  0017](../Decisions/0017-grayworld-white-balance-sim-to-real.md).
- **Default detection confidence lowered, 0.25 → 0.10** (`runYolo()`/
  `runYoloSeg()` in `lib/api.ts`, commit `fcc2773`) — the trained parts
  models score lower on real Zivid frames than on synthetic validation data
  (sim-to-real gap), so 0.25 hid almost every real detection. Both helpers
  still accept a per-call `opts.conf` override. See [ADR
  0017](../Decisions/0017-grayworld-white-balance-sim-to-real.md) for the
  companion fix (gray-world white balance on the Zivid capture) and why this
  is a stopgap, not a durable fix.
- **`SceneView`** (`frontend/src/components/SceneView.tsx`) — renders a
  captured RGB frame plus overlays in the image's **native pixel space**
  (an `<svg viewBox>` sized to the loaded image's natural dimensions) so
  `/infer` coordinates map 1:1 with no separate scaling step; box labels get
  a distinct color cycled per instance. `MaskCanvas` composites per-instance
  single-channel mask PNGs into one colored overlay canvas
  (threshold-per-pixel alpha). `DepthCanvas` renders the 16-bit-mm depth PNG
  as a min–max-normalized "turbo"-style heatmap — a **display aid only**
  (browsers downsample 16-bit PNGs to 8-bit on decode), not metric depth.
- **No new frontend test coverage.** `SceneView`, `SourceToggle`,
  `PartSelector`, and the rewritten `PerceptionPage.tsx` capture/inference
  flow have no Vitest tests as of this capture — see "Test suite" below.

## Pose pipeline selector (`RunControls`, added 2026-07-08, commit `2485997`)

Mirrors the orchestrator's `pose_pipeline`/`?pose_pipeline=` override (see
[System: Orchestrator](./orchestrator.md) "Pose pipeline selection" and
[ADR 0016](../Decisions/0016-gigapose-2d-planar-pose-mode.md)) — closes the
wiring gap that ADR flagged as still-open ("the orchestrator does not yet
call `pipeline='2d'`"), the operator can now pick it from the dashboard:

- **Pose selector** (`RunControls.tsx`, next to the robot-target toggle) —
  three buttons: `6DoF` (FoundationPose, depth, default), `6DoF·RGB`
  (GigaPose, RGB-only), `2D` (GigaPose CAD-free planar pose — no templates
  needed). Disabled under the same conditions as the robot-target toggle
  (run in progress, or *Dry run* checked — mocks ignore the pipeline).
  `onStart` passes `dryRun ? undefined : posePipeline` through to
  `useRunStream.start()` → `runStreamUrl()`'s `&pose_pipeline=` param
  (`DashboardPage.tsx`), same pattern as `robotTarget`.
- **State** — `posePipeline`/`setPosePipeline` live in `RunProvider`
  (`hooks/runContext.tsx`), shared across pages the same way `robotTarget`
  is; initial value comes from `RuntimeConfig.run.posePipeline`
  (`config/runtime.ts`, new field, default `"rgbd"`).
- **Settings default** — a new "Pose" dropdown under Settings → Run defaults
  (`SettingsPage.tsx`), persisted the same way as the other run defaults
  (`localStorage` override via "Save & reload").
- **`PosePipeline` type** (`lib/types.ts`) — `"rgbd" | "rgb" | "2d"`, added
  alongside `RobotTarget`; `RuntimeConfig.run` gained a `posePipeline` field.
- **No new frontend test coverage** for this selector as of this capture —
  see "Test suite" below.

## YOLO-Seg + manual image upload (added 2026-07-08)

Two independent additions to the Perception page, shipped together
(commit `27fee6c`):

- **`yoloseg` wired in as a fourth model choice**, and the two trained-parts
  models relabeled to disambiguate them from the open-vocab pair:
  `MODELS` (`PerceptionPage.tsx`) now lists `YOLO-Det` (was plain `YOLO` —
  the trained `parts_detmask` detector), `YOLO-Seg` (new — `parts_seg_v1`,
  **the default selected model** as of this change, was `sam3`), `SAM 3`,
  `LocateAnything`. The stale copy "YOLO uses its fixed COCO-80
  vocabulary — it won't recognise the disassembly parts" (accurate when
  `yolo` served stock weights, false since the detector was trained — see
  [ADR 0012](../Decisions/0012-mask-derived-detection-labels.md)) is
  **removed**; both YOLO variants now show a one-line description of the
  trained model instead. `runYoloSeg()` (`lib/api.ts`) posts to
  `{yoloseg}/infer` via the same `postInfer()` helper every other model
  uses. `YoloSegResponse`/`YoloSegInstance` (`lib/types.ts`) mirror the
  backend's `SegInstance` shape (`box`, `mask_b64_png`, `score`, `class_id`,
  `label`). YOLO-Seg results render through the same `SceneView`
  boxes/masks overlay `sam3` uses (`hasMasks = model === "sam3" || model ===
  "yoloseg"` now gates the masks/boxes toggle, previously `sam3`-only).
  `yoloseg` was added to the `ServiceKey` union, `SERVICE_KEYS`
  (`config/runtime.ts`), the `localhostDefaults()`/`envDefaults()` maps
  (`VITE_YOLOSEG_URL`, default `http://localhost:8007`),
  `ServiceHealthStrip`'s short-label map (`yolo` relabeled `yolo·det`,
  `yoloseg` added as `yolo·seg`), and `SettingsPage`'s label map (`YOLO-Det
  (parts)` / `YOLO-Seg (parts)`) — the same four-layer config precedence and
  health-check pattern as every other service (see "Runtime endpoint
  config" below). `deploy-local/config.json` (gitignored, machine-local —
  see [SOP: deploying perception to the GPU
  server](../SOP/deploy_perception_gpu_server.md)) points `yoloseg` at
  `http://127.0.0.1:18007`, the local end of the SSH tunnel to the
  GPU-server's `wbk-yoloseg` sidecar (see
  [ADR 0015](../Decisions/0015-yoloseg-sidecar-container-no-rebuild.md)).
- **Manual image upload** (`uploadImage()`, a new file-input button next to
  *Capture Zivid view*) — reads a locally chosen image via `FileReader`,
  strips the `data:...;base64,` prefix, and calls `setScene({rgb_b64: b64,
  backend: "upload"})` directly, bypassing `captureScene()` entirely. This
  is a **debug aid**: it lets inference be exercised against an arbitrary
  image (e.g. a real dataset frame) with no sim/Zivid/camera running at
  all, and works identically for all four models. `SceneCapture.backend`
  (a plain `string` field, not a closed union) is set to `"upload"` to
  record the provenance alongside whatever `"real"`/`"sim"` values
  `captureScene()` sets; the uploaded filename is shown next to the button
  and cleared on the next real/sim capture.
- **No new frontend test coverage** for either addition (`runYoloSeg`,
  `uploadImage`, the relabeled `MODELS`/`ServiceKey` wiring) — see "Test
  suite" below; `npm run build` (type-check) does cover the new types.

## Runtime endpoint config — the flexible bit (`frontend/src/config/runtime.ts`)

Every microservice (orchestrator, yolo, sam3, locateanything, foundationpose,
gigapose, damage, movement, grip, and — added 2026-07-08 —
`movementSim`/`gripSim` (the Isaac Sim backend/its optional grip endpoint)
and `sceneCapture` (the real Zivid `scene_camera` service, default
`http://localhost:9002`)) and both camera streams (sceneCamera,
inspectionCamera) can live on a **different host**. The simulator keys
default to **empty** — a blank `movementSim` is what `simAvailable` (see "Sim
/ digital-twin UI" above) checks to grey out Sim/Both. `frontend/public/config.json`'s
committed defaults for `yolo`/`sam3`/`locateanything`/`foundationpose`/`gigapose`
now point at `localhost:1800{1-5}` (was `800{1-5}`) — the SSH-tunnel port
convention from the split GPU-server deployment, see
[SOP: deploying perception to a remote GPU server](../SOP/deploy_perception_gpu_server.md);
`movement`/`grip` now default to `localhost:9000`/`9001` (was a hardcoded
Jetson IP) for the same local-tunnel convention.

`lib/types.ts`'s `RuntimeConfig`/patch-layer typing was refactored alongside
this: a new `ConfigPatch` type (`services`/`streams`/`run` all optional,
independently sparse) replaces ad hoc `Partial<RuntimeConfig>` casts across
`getOverrides()`/`saveOverrides()`/`envDefaults()`/`loadConfig()` — same
merge behavior, just a named, reusable shape instead of duplicated inline
`Partial<...>` annotations. `run` also gained `robotTarget: RobotTarget`
(default `"real"`, see `localhostDefaults()`) alongside the existing
`dryRun`/`stepDelayMs`.

Because this is a static
bundle, "different host per deploy" can't be a build-time-only decision —
`loadConfig()` (awaited once in `main.tsx` before the app renders) resolves
the final config by merging four layers, **later wins**:

1. **`localhostDefaults()`** — hardcoded `http://localhost:800N` fallbacks, so
   a bare `npm run dev` shows something with zero config.
2. **Build-time `VITE_*` env vars** (`frontend/.env.example` — copy to `.env`)
   — baked into the bundle at `npm run build` time.
3. **`frontend/public/config.json`** — fetched at runtime
   (`fetch("config.json", {cache: "no-store"})`, a relative path so it
   resolves under any base path). This file is **not baked into the bundle**
   — it's copied into the built image separately and bind-mounted read-only
   in `docker-compose.yml` (`./frontend/public/config.json:/usr/share/nginx/html/config.json:ro`),
   so editing it on the deployed machine and reloading the browser
   re-points every service **with no rebuild**. `nginx.conf` sends
   `Cache-Control: no-store` specifically for `/config.json` so this actually
   takes effect on reload.
4. **`localStorage` overrides** — live, per-browser edits from the Settings
   page (`saveOverrides()`/`getOverrides()`/`clearOverrides()`, key
   `wbk.config.overrides`). Reload-to-apply (`window.location.reload()` after
   save).

So precedence, later/higher wins: **localStorage > config.json > VITE_\* >
localhost**. `merge()` is a shallow-per-section merge (`services`/`streams`/
`run` each merged independently); `stripTrailingSlashes()` runs once at the
end so downstream URL-joining (`lib/api.ts`) doesn't have to guard against a
trailing slash.

`getConfig()`/`serviceUrl(key)`/`streamUrl(key)` read the already-resolved
module-level `current` config synchronously anywhere in the app after the
initial `loadConfig()` await.

## Auth token (`apiToken`, `frontend/src/lib/api.ts`)

The runtime config carries one more field, `apiToken` (`lib/types.ts`,
default `""`, resolved through the same four-layer precedence above —
notably `VITE_API_TOKEN` at the build-time layer and a live-editable
"API token" field on the Settings page). It is the shared token described in
[ADR 0009](../Decisions/0009-shared-token-auth.md), and is attached two
different ways depending on the transport:

- `authHeaders()` returns `{"Authorization": "Bearer <token>"}` (or `{}` if
  unset) — sent on `POST /run` (`runOnce()`).
- `runStreamUrl()` appends `&token=<token>` to the `GET /events/run` URL
  instead, because the SSE consumer is a browser `EventSource`, which cannot
  set request headers.

Same rules as every other service: if the orchestrator has no
`WBK_API_TOKEN` configured, an empty `apiToken` here works fine (auth is
opt-in end to end). If the orchestrator *does* have a token configured, this
field must match it or `POST /run`/`GET /events/run` 401.

## Consuming the orchestrator's live loop (`frontend/src/hooks/useRunStream.ts`)

`useRunStream()` wraps a browser `EventSource` against
`runStreamUrl(dryRun, delaySeconds, target?, product?)` (`lib/api.ts`), which
points at the orchestrator's
`GET /events/run?dry_run=...&delay=...&target=...&product=...` (`target`
and `product` both added 2026-07-08 — see
[System: Orchestrator](./orchestrator.md) and
[Integration Points](./integration_points.md) for the wire contract). Key
behavior:

- A named `start` SSE listener (added alongside `target`) parses the
  server's opening frame and sets `activeTarget` (`RunStreamState`) — the
  robot the server actually drove, which the UI badges next to the run
  status (see "Sim / digital-twin UI" above).
- Named SSE listeners for `event` (append to `events: LoopEvent[]`),
  `summary` (set `stats: RunStats`), `error` (a **named** server-sent error
  frame — a run failure, not a transport error — sets `status: "error"` and
  closes), and `end` (marks `status: "done"` and **closes the EventSource**).
- Closing on `end` is load-bearing: `EventSource` auto-reconnects by default,
  and the orchestrator's `GET /events/run` **starts a new loop run** on every
  connection — so failing to close on `end` would silently kick off a second
  run. The comment at the top of the file calls this out explicitly.
- `es.onerror` (the transport-level handler, distinct from the named `error`
  event above) only sets `status: "error"` if a run was actually `"running"`
  — this is what surfaces "connection to orchestrator lost" if the stream
  drops mid-run, without misfiring after a clean `end`.

`frontend/src/hooks/runContext.tsx` (`RunProvider`/`useRun`) lifts one
`useRunStream()` instance to the app root so Dashboard/Perception/Inspection
all read the same live run state across client-side navigation, plus
UI-level state that isn't part of the stream itself (`dryRun`, `delayMs`,
`prompt`, and — added 2026-07-08 — `robotTarget`/`setRobotTarget`,
`sourceMode`/`setSourceMode` (see "Sim / digital-twin UI" above), and
`product`/`setProduct` (plan-driven runs, see "Plan mode UI" above)).

`frontend/src/hooks/useServiceHealth.ts` independently polls every service's
`GET /health` on a 5s interval (`checkHealth()` in `lib/api.ts`) — unrelated
to the SSE stream, used for the health strip.

## Stage mapping (`frontend/src/lib/stages.ts`)

Mirrors `orchestrator/loop.py`'s `LoopEvent.state` values onto the 7
UI-facing stages: `GRIP`/`REGRASP`/`SKIP` → `GRASP`; `REMOVE`/`RECHECK` →
`REMOVE`; `LOCATE`/`POSE`/`SORT` map 1:1; `DONE`/`BLOCKED`/`SUMMARY` (and, as
of 2026-07-08, `PLAN_GENERATED`) map to `null` (terminal/non-stage, not
shown as an active pipeline stage). `STEP` narration doesn't map to a stage
either — `PlanProgress` renders it, not `StageTracker`. `STATE_STYLE` gives
each raw state a Tailwind pill style for the event log (e.g. `REGRASP` and
`BLOCKED` both read amber/rose to read as attention-worthy; `PLAN_GENERATED`/
`STEP` read fuchsia as the plan-mode-specific states, `GUARDRAIL` reads
amber alongside the other attention states). `frontend/src/lib/types.ts`
mirrors `orchestrator/models.py`'s `LoopEvent`/stats shapes on the
TypeScript side, including the plan-mode `LoopState` additions
(`PLAN_GENERATED`, `STEP`, `GUARDRAIL`) and the `ErpProduct`/`PlanStepPreview`
shapes for `/products`/`/plan` — keep these in sync if the Python dataclasses
change shape.

## Test suite (`frontend/src/lib/derive.ts` + Vitest)

The event-reducer logic that used to live inline in components was pulled
out into pure functions in `frontend/src/lib/derive.ts` specifically to make
it unit-testable without rendering:

- `tallyBins(events, stats)` → bin counts, consumed by `BinTally`.
- `deriveInspections(events)` → per-part OK/damaged verdicts, consumed by
  `InspectionPage`.
- `deriveGrip(events)` → `{ attempts, confirmed, retrying }`, consumed by
  `GripTelemetry`.
- `currentPart(events)` → the active part/step derived from the latest
  `LOCATE` event, consumed by `DashboardPage`.
- `derivePlan(events)` (added 2026-07-08) → the `PlanProgress` checklist
  (`source` + per-step `pending`/`active`/`done`/`skipped`/`blocked` status),
  built from the `PLAN_GENERATED` event plus `STEP`/`SORT`/`SKIP`/`BLOCKED`
  progress events; returns `null` when no `PLAN_GENERATED` event exists yet
  (fixed-mode runs never render `PlanProgress`).

`npm test` (`vitest run`, jsdom env) runs 30 tests across 4 files:
`src/lib/derive.test.ts` (16, the reducers above — 4 new cases cover
`derivePlan`), `src/config/runtime.test.ts`
(6, the four-layer endpoint-precedence resolution described above —
localStorage > config.json > env > localhost, trailing-slash stripping,
fetch-failure fallback), `src/lib/stages.test.ts` (5, the
`stateToStage` mapping described below), and `src/lib/api.test.ts` (3, the
`apiToken`/auth-token wiring above — `authHeaders()` empty vs. Bearer header,
`runStreamUrl()` appending `?token=`). All passing; wired into CI as
`npm test` ahead of `npm run build` in the `frontend` job of
`.github/workflows/tests.yml` — see [System: Architecture](./architecture.md#test-suite).
Still **30 tests** as of 2026-07-08 — the sim/digital-twin UI added that day
(`SceneView`, `SourceToggle`, `PartSelector`, the rewritten `PerceptionPage.tsx`
capture/inference flow, `captureScene`/`generateScenePreview`/`runYolo`/
`runSam3`/`runLocate` in `lib/api.ts`) shipped with no new Vitest coverage —
a gap, not a claim of coverage. The same-day `yoloseg`/manual-image-upload
follow-up (`runYoloSeg`, `uploadImage`, the `MODELS`/`ServiceKey` relabeling —
see "YOLO-Seg + manual image upload" above) is the same story: no new
Vitest cases, still 30. `npm run build` (type-check) does cover it,
since `SceneView`'s prop types and `lib/types.ts`'s new shapes
(`SourceMode`, `RobotTarget`, `ConfigPatch`, the perception result types)
must still typecheck.

## Deployment

- `frontend/Dockerfile` — multi-stage: `node:22-alpine` runs `npm ci && npm
  run build`, then `nginx:1.27-alpine` serves `dist/` on port 80.
  `public/config.json` is deliberately **not** part of the baked image layer
  in the sense that matters — the compose volume mount overlays it at
  container start, so the same image works across deployments.
- `frontend/nginx.conf` — `no-store` on `/config.json`; `try_files ... /
  index.html` fallback for the `HashRouter` SPA.
- `docker-compose.yml`'s `dashboard` service — builds from `./frontend`,
  maps host `5173` → container `80`, mounts
  `./frontend/public/config.json:/usr/share/nginx/html/config.json:ro`.

## Works today against mocks

Same mock-first posture as the orchestrator itself
(see [ADR 0005](../Decisions/0005-mock-first-interface-seam-integration.md)):
start the orchestrator (`uvicorn orchestrator.app:app`), open the dashboard,
leave *Dry run* on, hit Start — the full loop streams through the UI,
including the grasp-failure → `REGRASP` recovery path and a damaged part
routing to the reject bin, with no GPU/services/hardware required.
