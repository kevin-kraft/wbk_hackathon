# ADR 0008 — Dashboard is a separate static app, not fused into the orchestrator

## Related Docs
- [System: Dashboard](../System/dashboard.md) — architecture, pages, runtime-config precedence
- [System: Orchestrator](../System/orchestrator.md) — the `GET /events/run` SSE endpoint the dashboard consumes
- [System: Integration Points](../System/integration_points.md) — the SSE contract + CORS
- [ADR 0005: mock-first, interface-seam integration](./0005-mock-first-interface-seam-integration.md) — same "keep the control plane swappable" spirit, applied one layer up

## Context

A frontend was needed as an operator console and a live demo UI: run
controls, a 7-stage pipeline tracker, camera views, grip telemetry, damage
verdicts, bin tallies. The orchestrator (`orchestrator/app.py`) already had a
`POST /run` endpoint returning the full event list after the loop completes —
the natural question was whether the UI should be served *by* the
orchestrator itself (one FastAPI app, templates or a mounted SPA) or built as
its own independently deployable app.

## Decision

Build the dashboard as a **separate static app** (`frontend/`, React 19 + Vite
6 + TypeScript + Tailwind v4), built to a static bundle and served by its own
nginx container (`frontend/Dockerfile`, `dashboard` service in
`docker-compose.yml`, port `:5173`). It talks to the orchestrator and every
other stage purely over HTTP/SSE from the browser — no server-side coupling,
no shared process, no templating.

The only coupling between the two is a **read-only** event stream: the
orchestrator's `GET /events/run` SSE endpoint (see
[System: Orchestrator](../System/orchestrator.md)). The dashboard is a pure
consumer; it can never call back into the loop except through the same
`POST /run` / `GET /events/run` surface any other client would use.

## Rationale

- **The orchestrator is a headless control plane.** It drives GPU services
  and physical hardware (the Jetson arm, the grip sensor) and must keep
  running unattended — a demo laptop closing its browser tab, or an operator
  reloading the page mid-disassembly, must not affect an in-flight
  disassembly loop. Fusing the UI in would tie the control loop's lifecycle
  to a browser session.
- **CI-testability.** `orchestrator/`'s test suite (`tests/orchestrator/`)
  runs with no `httpx`/`cv2`/`numpy`, let alone a browser — see
  [ADR 0005](./0005-mock-first-interface-seam-integration.md). Bundling a
  frontend build step into that package would drag `npm`/`node`/`vite` into
  the Python test/CI path for no testing benefit.
- **Independent, per-host deployability.** Every microservice in this repo
  (perception, pose, damage, orchestrator) can already live on a different
  host — see [Architecture](../System/architecture.md). The dashboard needs
  the same property: it must be deployable to any machine (a demo laptop, an
  ops box on the LAN) and re-pointed at wherever each service actually runs,
  without rebuilding the orchestrator or recompiling the dashboard itself.
  This is why runtime endpoint config (`frontend/public/config.json` +
  Settings-page localStorage overrides) exists — see
  [System: Dashboard](../System/dashboard.md) for the full precedence chain.
- **Cross-origin is a small, well-understood cost.** Splitting the apps means
  the dashboard's browser calls the orchestrator cross-origin, so the
  orchestrator now runs permissive CORS middleware
  (`allow_origins=["*"]`, see [Integration Points](../System/integration_points.md)).
  This is judged acceptable for a trusted-LAN hackathon control plane; it
  would need tightening (to the known dashboard origin(s)) before any wider
  exposure.

## Alternatives considered

- **Serve the SPA from the orchestrator's FastAPI app** (mount `dist/` as
  static files, or server-render). Rejected: couples UI deploys to
  orchestrator deploys, pulls a Node build step into the Python
  package/container, and removes the "reload the browser without touching
  the loop" property.
- **A single combined container/process.** Rejected for the same reasons,
  plus it removes the ability to run the dashboard on a different host than
  the orchestrator (useful when the orchestrator runs headless near the arm
  and the operator views the dashboard from a laptop).

## Consequences

- The orchestrator needs CORS middleware it wouldn't otherwise need (see
  above) — a permissive `allow_origins=["*"]`, explicitly flagged as
  demo/trusted-LAN-appropriate, not hardened for public exposure.
- The dashboard cannot assume same-origin cookies/sessions with the
  orchestrator — today neither app has auth, so this isn't yet felt, but any
  future auth layer will need to be designed cross-origin (tokens, not
  cookies) from the start.
- Two independent build/deploy pipelines (Python/uv for the backend stages,
  npm/vite for the frontend) instead of one — judged worth it for the
  deployability and CI-isolation gains above.
