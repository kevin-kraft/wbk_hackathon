# Dashboard (`frontend/`) — operator console + live demo UI

## Related Docs
- [Architecture](./architecture.md) — full pipeline overview, per-stage service map
- [System: Orchestrator](./orchestrator.md) — the `GET /events/run` SSE endpoint this app consumes, and `LoopEvent`/loop-state shapes it mirrors
- [Integration Points & Wire Contracts](./integration_points.md) — the SSE event contract + CORS
- [ADR 0008: dashboard is a separate static app](../Decisions/0008-frontend-separate-static-app.md) — why this isn't fused into the orchestrator
- [ADR 0009: shared-token auth](../Decisions/0009-shared-token-auth.md) — the `apiToken` field below, and why `GET /events/run` needed a query-param token transport
- [ADR 0011: LLM action selector, constrained vocabulary](../Decisions/0011-llm-action-selector-constrained-vocabulary.md) — the `GUARDRAIL` event `PlanProgress`/the event log surface
- [ADR 0014: robot target selection (real \| sim \| both)](../Decisions/0014-robot-target-real-sim-both.md) — the Real/Sim/Both toggle this doc's "Sim / digital-twin UI" section covers
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
| Dashboard | `DashboardPage.tsx` | Run controls (start/stop, dry-run toggle, pace/delay, `ProductSelector` — see "Plan mode UI" below), the 7-stage pipeline tracker (`StageTracker`) driven by the *latest* live event, `PlanProgress` (plan-driven runs only), scene camera (`MjpegView`), grip telemetry, a next-part text prompt box, bin tallies, and the full event log. |
| Perception | `PerceptionPage.tsx` | Scene view plus the YOLO / SAM 3 / LocateAnything endpoints and their `/health` status (detection overlays are noted as future work, not yet rendered). |
| Inspection | `InspectionPage.tsx` | Inspection camera, the damage-VLM endpoint, a per-part OK/damaged verdicts table, and bin state. |
| Settings | `SettingsPage.tsx` | Live-editable text fields for every service endpoint and both camera stream URLs, plus run defaults (dry-run, pace) and the shared `apiToken` (see "Auth token" below); "Save & reload" persists to `localStorage`, "Reset to config.json" clears the override. |

Shared building blocks in `frontend/src/components/`: `Layout`, `StageTracker`
(maps loop state → one of the 7 canonical stages, see `lib/stages.ts`),
`EventLog`, `GripTelemetry`, `BinTally`, `PromptBox`, `MjpegView` (raw
`<img>`-based MJPEG viewer), `ServiceHealthStrip`, `ServiceInfo`, `ui.tsx`
(`Card`, etc.) primitives, and (added 2026-07-08, see "Plan mode UI" below)
`ProductSelector` and `PlanProgress`.

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

## Runtime endpoint config — the flexible bit (`frontend/src/config/runtime.ts`)

Every microservice (orchestrator, yolo, sam3, locateanything, foundationpose,
gigapose, damage, movement, grip) and both camera streams (sceneCamera,
inspectionCamera) can live on a **different host**. Because this is a static
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
`runStreamUrl(dryRun, delaySeconds)` (`lib/api.ts`), which points at the
orchestrator's `GET /events/run?dry_run=...&delay=...` (see
[System: Orchestrator](./orchestrator.md) and
[Integration Points](./integration_points.md) for the wire contract). Key
behavior:

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
`prompt`).

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
