# ADR 0009 — Optional shared-token auth on work + robot endpoints

## Related Docs
- [System: Integration Points](../System/integration_points.md) — the per-contract token requirement + the two transports
- [System: Orchestrator](../System/orchestrator.md) — `/run`/`/events/run` gated, `auth_headers` sent downstream
- [System: Dashboard](../System/dashboard.md) — the Settings-page `apiToken` field and how it's attached
- [ADR 0008: dashboard is a separate static app](./0008-frontend-separate-static-app.md) — flagged this gap in its "Consequences" section ("today neither app has auth... any future auth layer will need to be designed cross-origin")
- [SOP: running the services](../SOP/running_services.md) — `WBK_API_TOKEN` in compose/deploy env

## Context

Every service in this repo (perception, pose, damage, orchestrator) is a bare
FastAPI app with no auth of any kind, deployed on a LAN that may include
untrusted or semi-trusted co-tenants (a shared demo network, a shared GPU
host). ADR 0008 already flagged this as an open gap when the dashboard went
cross-origin. The concrete risk being closed here is casual/accidental
misuse from **other machines on the network** — someone scanning ports,
another team's script hitting the wrong host, a stray `curl` — not a
determined attacker with shell access to the same host.

Constraints that shaped the design:
- Must not break `dry_run` demos, CI, or the mock-first posture (ADR 0005) —
  none of those make real network calls, so auth must be opt-in.
- The dashboard is a **browser** SSE consumer (`EventSource`), which cannot
  set custom headers — any token scheme must also work as a URL parameter.
- Four independently deployable packages (`perception/`, `pose/`, `damage/`,
  `orchestrator/`) each need the same check with no shared importable
  package between them (they run from different roots at deploy time — see
  [SOP: running the tests](../SOP/running_tests.md) on the `conftest.py`
  import-root split).

## Decision

An **optional shared bearer token**, env `WBK_API_TOKEN`. A small FastAPI
dependency `require_token` — the same ~35-line implementation copy-pasted
into each deployable package (`perception/services/shared/auth.py`,
`pose/shared/auth.py`, `damage/auth.py`, `orchestrator/auth.py`) rather than
imported from one shared location, because there is no shared import root
across those four packages at deploy time. Reads `WBK_API_TOKEN` from the
environment **at request time**; unset = auth disabled, so dev/CI/mocks/
dry-run are unaffected without any extra flag.

**Protected endpoints** ("work + robot" scope only):

| Service | Endpoint |
|---|---|
| perception (yolo/sam3/locateanything) | `POST /infer` |
| pose (foundationpose/gigapose) | `POST /pose` |
| damage | `POST /inspect` |
| orchestrator | `POST /run`, `GET /events/run` |

`GET /health` (and `/`) stay open on every service, so monitoring/health
strips work without a token. The teammate-owned Jetson endpoints
(`movement_url`/`grip_url`, `HttpMovement`/`HttpGrip`) are explicitly **out
of scope** — they're not this repo's services, and the orchestrator's
clients for them do not attach `auth_headers`.

**Transport**: `Authorization: Bearer <token>` header, **or** `?token=<token>`
query param. The query form exists solely because browser `EventSource`
(the dashboard's SSE consumer) cannot set headers — see
[System: Dashboard](../System/dashboard.md). Comparison is constant-time
(`secrets.compare_digest`); missing or wrong token → 401.

**Orchestrator is both enforcer and caller.** It requires the token on its
own `POST /run`/`GET /events/run` (via `Depends(require_token)`) *and*
attaches it to every outbound perception/pose/damage request
(`OrchestratorConfig.auth_headers` → `Authorization: Bearer …`, set on the
`httpx.Client(headers=...)` for `HttpPerception`/`HttpPose`/`HttpDamage`).
One env var, `WBK_API_TOKEN`, has to match across every deployed instance —
there's no per-service token issuance.

**Dashboard**: a new `apiToken` field in the runtime config
(`frontend/src/config/runtime.ts`, `frontend/src/lib/types.ts`), editable on
the Settings page, sent as an `Authorization: Bearer` header on `POST /run`
(`lib/api.ts:authHeaders()`) and appended as `?token=` on the `GET
/events/run` SSE URL (`lib/api.ts:runStreamUrl()`).

## Alternatives rejected

- **CORS as the access control.** Already permissive (`allow_origins=["*"]`,
  ADR 0008) and was never intended as a security boundary — CORS is enforced
  by the browser, not the server, so it does nothing against a non-browser
  client (`curl`, a script) hitting the API directly.
- **IP allowlisting.** Rejected as brittle: hosts on the demo LAN
  (laptops, the Jetson, GPU rentals) don't have stable IPs, and rebuilding
  an allowlist every time someone reconnects is worse UX than a shared
  token for a hackathon-scale deployment.
- **A real auth system (OAuth/JWT/per-user accounts).** Overkill for a
  handful of trusted services on a demo LAN with no end-user accounts to
  speak of; would add a dependency (an identity provider or a signing
  keypair to manage) for a threat model that doesn't need it.

## Consequences

- **This is a trusted-LAN anti-spam gate, not a real security boundary** —
  the important caveat to remember before relying on it for anything beyond
  "keep casual network noise out":
  - On a **shared host**, a co-tenant with any read access can recover the
    token from the process environment, a mounted `.env` file, `docker
    inspect`, or `/proc/<pid>/environ` — it blocks network-only outsiders,
    **not** same-host co-tenants.
  - A **browser-embedded token is visible in devtools** (Settings page
    input, `localStorage`, outgoing request headers/URLs) — anyone with
    access to the operator's browser session can read it.
  - The mitigation for both is **service placement**, not a stronger token
    scheme: keep the `OPENROUTER_API_KEY`-holding damage service and the
    orchestrator on hosts you don't share with untrusted co-tenants. Revisit
    if the deployment model changes (e.g. a genuinely public demo).
- `dry_run`/mocks/CI need zero changes — `WBK_API_TOKEN` unset is the
  default in every test and dry-run path, so `require_token` is a no-op
  there.
- One token to rotate across every deployed service + the dashboard's
  Settings field — no per-service secrets, which is the point (simplicity)
  but also means a leak anywhere requires rotating everywhere.
- Test cost: +19 Python tests (`tests/{orchestrator,damage,perception,pose}/test_auth.py`,
  105 total) and +3 frontend tests (`frontend/src/lib/api.test.ts`, 26
  total) — see [System: Architecture](../System/architecture.md#test-suite).
