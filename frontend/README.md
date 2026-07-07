# Dashboard (frontend)

Operator console + live demo UI for the VLM-guided disassembly pipeline. A
**separate static app** (React + Vite + TypeScript + Tailwind) that talks to the
orchestrator and the other services over HTTP — deliberately *not* fused with the
orchestrator, so it deploys anywhere and re-points at services on any host.

## Why separate from the orchestrator

The orchestrator is a headless control plane: a state machine driving GPU
services and physical hardware that must run autonomously (no browser), survive a
UI reload mid-disassembly, and stay testable in CI. The dashboard is a browser
app. Keeping them apart lets each microservice live on a different machine and the
UI be re-pointed without touching the control loop. The only coupling is a
read-only event stream (SSE) the orchestrator exposes.

## The pages

| Page | What it shows |
|---|---|
| **Dashboard** | Run controls (start/stop, dry-run, pace), the 7-stage pipeline tracker with the live REGRASP retry, scene camera, grip telemetry, next-part prompt, bin tallies, and the event log. |
| **Perception** | Scene view + YOLO / SAM 3 / LocateAnything endpoints & health (detection overlays are future work). |
| **Inspection** | Inspection camera, damage-VLM endpoint, per-part OK/damaged verdicts, bins. |
| **Settings** | Live-editable endpoints for every service + camera streams + run defaults. |

## Configuring endpoints (the flexible bit)

Every microservice can live on a different host. Resolution order (later wins):

1. `localhost` fallbacks
2. build-time `VITE_*` env vars (see `.env.example`) — baked defaults
3. **`public/config.json`** — edit on the deployed machine, **no rebuild**
4. **Settings page** — live per-browser overrides (stored in `localStorage`)

For a deployment, the intended path is #3: edit `public/config.json` (mounted into
the container, see `docker-compose.yml`) and reload. For quick demo tweaks, use the
Settings page.

```jsonc
// public/config.json
{
  "services": {
    "orchestrator": "http://10.0.0.5:8000",
    "yolo":         "http://10.0.0.6:8001",
    "damage":       "http://10.0.0.7:8006"
    // ...movement / grip on the Jetson, etc.
  },
  "streams": { "sceneCamera": "http://10.0.0.9:8080/stream.mjpg" },
  "run":     { "dryRun": true, "stepDelayMs": 700 }
}
```

## Run it

```bash
npm install
npm run dev        # http://localhost:5173 (dev server)

npm run build      # type-check + production bundle to dist/
npm run preview    # serve the built bundle

# or containerized (serves on :5173, config.json mounted):
docker compose up --build dashboard
```

The dashboard works **today against mocks**: start the orchestrator
(`uvicorn orchestrator.app:app`), open the dashboard, keep *Dry run* on, and hit
Start — you'll watch the full loop stream, including the grasp-failure→REGRASP
recovery and the damaged part going to the reject bin.

## How the live loop is consumed

The orchestrator exposes `GET /events/run?dry_run=<bool>&delay=<seconds>` as a
Server-Sent Events stream. Each stage emits a named `event` frame
(`{step, state, message, data}`), a `summary` frame carries the final stats, and an
`end` frame closes the stream. `delay` paces emission so the demo is watchable.
The `useRunStream` hook opens an `EventSource`, accumulates events, and closes on
`end` (so it never auto-reconnects into a second run).

## Layout

```
public/config.json      runtime endpoint config (editable post-build)
src/
  config/runtime.ts      config loader (env < config.json < localStorage)
  lib/                   types, api helpers, stage mapping
  hooks/                 useRunStream (SSE), useServiceHealth, runContext
  components/            Layout, StageTracker, EventLog, GripTelemetry, ...
  pages/                 Dashboard, Perception, Inspection, Settings
```
