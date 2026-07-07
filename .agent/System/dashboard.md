# Dashboard (`frontend/`) — operator console + live demo UI

## Related Docs
- [Architecture](./architecture.md) — full pipeline overview, per-stage service map
- [System: Orchestrator](./orchestrator.md) — the `GET /events/run` SSE endpoint this app consumes, and `LoopEvent`/loop-state shapes it mirrors
- [Integration Points & Wire Contracts](./integration_points.md) — the SSE event contract + CORS
- [ADR 0008: dashboard is a separate static app](../Decisions/0008-frontend-separate-static-app.md) — why this isn't fused into the orchestrator
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

## The four pages (`frontend/src/pages/`)

| Page | File | What it shows |
|---|---|---|
| Dashboard | `DashboardPage.tsx` | Run controls (start/stop, dry-run toggle, pace/delay), the 7-stage pipeline tracker (`StageTracker`) driven by the *latest* live event, scene camera (`MjpegView`), grip telemetry, a next-part text prompt box, bin tallies, and the full event log. |
| Perception | `PerceptionPage.tsx` | Scene view plus the YOLO / SAM 3 / LocateAnything endpoints and their `/health` status (detection overlays are noted as future work, not yet rendered). |
| Inspection | `InspectionPage.tsx` | Inspection camera, the damage-VLM endpoint, a per-part OK/damaged verdicts table, and bin state. |
| Settings | `SettingsPage.tsx` | Live-editable text fields for every service endpoint and both camera stream URLs, plus run defaults (dry-run, pace); "Save & reload" persists to `localStorage`, "Reset to config.json" clears the override. |

Shared building blocks in `frontend/src/components/`: `Layout`, `StageTracker`
(maps loop state → one of the 7 canonical stages, see `lib/stages.ts`),
`EventLog`, `GripTelemetry`, `BinTally`, `PromptBox`, `MjpegView` (raw
`<img>`-based MJPEG viewer), `ServiceHealthStrip`, `ServiceInfo`, and a small
`ui.tsx` (`Card`, etc.) primitives file.

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
`REMOVE`; `LOCATE`/`POSE`/`SORT` map 1:1; `DONE`/`BLOCKED`/`SUMMARY` map to
`null` (terminal/non-stage, not shown as an active pipeline stage).
`STATE_STYLE` gives each raw state a Tailwind pill style for the event log
(e.g. `REGRASP` and `BLOCKED` both read amber/rose to read as
attention-worthy). `frontend/src/lib/types.ts` mirrors
`orchestrator/models.py`'s `LoopEvent`/stats shapes on the TypeScript side —
keep these two in sync if the Python dataclasses change shape.

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
