# Changelog (`.agent/` documentation)

Newest first.

- 2026-07-07 — Remote GPU-server deployment of perception documented as
  **in progress** (commit `5fbacdf`, "perception: parametrize base image via
  BASE_IMAGE build-arg", plus uncommitted `perception/README.md` additions
  at the time of this doc update). Added
  `SOP/deploy_perception_gpu_server.md`: the `ARG BASE_IMAGE` override
  needed for Blackwell GPUs (sm_120, e.g. RTX PRO 6000 →
  `pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel`, verified `torch
  2.8.0+cu128`/`transformers 4.57.1`/`ultralytics 8.4.90`), why
  `requirements.txt` omits torch, the rsync-instead-of-redownload weights
  recipe for a server with no HF auth (gated SAM 3 + LocateAnything-3B),
  running the container bound to `127.0.0.1:6767-6769` on the server, and
  the SSH port-forward tunnel (`-L 8001:localhost:6767` etc.) that lets the
  orchestrator's existing `PERCEPTION_*_URL` defaults
  (`http://localhost:800{1,2,3}`) keep working unchanged. Documented the
  intended split — orchestrator + damage + dashboard local, perception +
  pose on the GPU server — and the shared-Docker-daemon
  no-isolation-from-co-tenants caveat (secrets stay off the box). Explicitly
  flagged as **not yet a working deployment**: image built + weights
  rsync'ing, container not yet started, tunnel not yet established, pose not
  started. Extended `System/architecture.md`'s Stage 1 Perception section
  with the `ARG BASE_IMAGE` parametrization and a link to the new SOP (also
  added to that doc's Related Docs). Extended
  `SOP/running_services.md`'s perception section with the Blackwell
  build-arg override and a pointer to the new SOP (also added to its
  Related Docs). Added the new SOP to `README.md`'s SOP index, marked
  in-progress.
- 2026-07-07 — Shared-token auth (`WBK_API_TOKEN`) documented as **implemented**
  (commit `749b179`, "feat(auth): shared-token gate on work + robot
  endpoints") — previously only anticipated as a gap in ADR 0008's
  "Consequences". Added `Decisions/0009-shared-token-auth.md` (ADR: optional
  bearer token via a `require_token` FastAPI dependency copy-pasted into
  each of the four deployable packages — `perception/services/shared/auth.py`,
  `pose/shared/auth.py`, `damage/auth.py`, `orchestrator/auth.py` —
  unset-token = disabled; protects perception `POST /infer`, pose `POST
  /pose`, damage `POST /inspect`, orchestrator `POST /run`/`GET /events/run`;
  `GET /health` always open; header or `?token=` query transport, the latter
  for browser `EventSource`; alternatives rejected — CORS as a control, IP
  allowlisting, a real OAuth/JWT system; explicit **trusted-LAN-only** caveat
  — blocks network-only outsiders, not same-host co-tenants who can read the
  token from env/`.env`/`docker inspect`/`/proc`, nor a browser-embedded
  token visible in devtools; mitigation is service placement, revisited
  later). Extended `System/integration_points.md`: new auth bullet in the
  shared design-conventions list, a token-requirement note under each of
  Contracts 1–3, and the SSE contract's `?token=` transport explained under
  Contract 4. Extended `System/orchestrator.md`: new "Auth" section
  (`orchestrator/auth.py` enforces on `/run`+`/events/run`;
  `OrchestratorConfig.auth_headers` attaches the same token to
  `HttpPerception`/`HttpPose`/`HttpDamage`, explicitly **not**
  `HttpMovement`/`HttpGrip`); entry-point bullets and the Tests section
  updated. Extended `System/dashboard.md`: new "Auth token" section for the
  `apiToken` runtime-config field (`lib/api.ts`'s `authHeaders()` vs.
  `runStreamUrl()`'s `?token=`), Settings-page table row, and the Test suite
  paragraph. Updated Python test count 86 → 105 everywhere it was cited
  (`System/architecture.md`, `System/orchestrator.md`,
  `SOP/running_tests.md`, incl. the previously-stale "81 tests" in that
  SOP's `uv run pytest` comment) and added the new `test_auth.py` files (4
  each in `tests/{perception,pose,damage}/`, 7 in `tests/orchestrator/`) —
  plus a previously-missing `tests/orchestrator/` block — to
  `SOP/running_tests.md`'s Layout tree. Updated frontend test count 23 → 26
  everywhere it was cited (`System/architecture.md`, `System/dashboard.md`)
  for the new `frontend/src/lib/api.test.ts`. Added a `WBK_API_TOKEN` auth
  note (curl `-H` flag, opt-in default) to `SOP/running_services.md`. Added
  ADR 0009 to the `README.md` index and to the Related-Docs cross-links in
  `System/architecture.md`, `System/integration_points.md`,
  `System/orchestrator.md`, `System/dashboard.md`, and
  `SOP/running_services.md`/`SOP/running_tests.md`.
- 2026-07-07 — Correction: frontend now has a test suite. A Vitest unit
  suite landed in `frontend/` (`npm test` → `vitest run`, jsdom env,
  `frontend/vitest.config.ts`, `src/**/*.test.ts` — 23 tests across 3 files,
  all passing), and the event-reducer logic was extracted from components
  into pure functions in `frontend/src/lib/derive.ts` (`tallyBins`,
  `deriveInspections`, `deriveGrip`, `currentPart`) specifically to make it
  testable without rendering; `BinTally`/`GripTelemetry`/`InspectionPage`/
  `DashboardPage` now consume those. `.github/workflows/tests.yml`'s
  `frontend` job now runs `npm test` before `npm run build`, so unit tests +
  type-check + build all gate every push/PR (the `pytest` job is unchanged
  at 86 tests). Updated `System/architecture.md`'s "Test suite" section
  (previously said the frontend had no test framework and wasn't in CI —
  both now false) and `System/dashboard.md` (previously said "no test
  framework installed"; replaced with a new "Test suite" section detailing
  the Vitest setup, what each of the 3 test files covers, and the
  `lib/derive.ts` pure-reducer extraction). No README index changes needed —
  the existing one-liners for those two docs were generic and didn't assert
  the missing-test-framework state.
- 2026-07-07 — Dashboard (`frontend/`) and the orchestrator's SSE live-run
  endpoint documented (uncommitted working-tree changes as of this doc
  update: new `frontend/` tree, modified `orchestrator/app.py`,
  `docker-compose.yml`, root `README.md`). Added `System/dashboard.md`
  (React 19 + Vite 6 + TS + Tailwind v4 static SPA; the four pages; the
  four-layer runtime endpoint config `localStorage > config.json > VITE_* >
  localhost` in `frontend/src/config/runtime.ts`; `useRunStream`'s SSE
  consumption and the must-close-on-`end` gotcha; deployment via
  `frontend/Dockerfile` + nginx + the `dashboard` compose service; no test
  framework installed, `npm run build` is the only current gate and it is
  not in CI). Added `Decisions/0008-frontend-separate-static-app.md` (ADR:
  the dashboard is a separate static app, not served by the orchestrator —
  headless/CI-testable control plane vs. re-pointable-per-host browser app;
  the only coupling is the read-only `GET /events/run` SSE stream; CORS
  consequence). Extended `System/orchestrator.md` ("Entry points"): new
  `GET /events/run?dry_run=<bool>&delay=<seconds>` SSE endpoint (worker
  thread + `queue.Queue` bridging into an async generator, frame sequence,
  `delay` pacing) and the new permissive CORS middleware, both cross-linked
  to ADR 0008. Extended `System/integration_points.md`: new "Contract 4 —
  Orchestrator live loop `GET /events/run` (SSE)" section (full frame-type
  table, the close-on-`end` consumer contract, the CORS note). Updated
  `System/architecture.md`: pipeline diagram gained the dashboard as a
  read-only SSE observer, stage table gained a `Dashboard (UI)` row
  (`frontend/`, `:5173`, nginx), and the Test suite section now notes the
  86-pytest count is Python-only (`frontend/` has no test framework; `npm
  run build` is clean but not wired into `.github/workflows/tests.yml`).
  Updated `README.md`'s `System/integration_points.md` and
  `System/orchestrator.md` lines, added the `System/dashboard.md` and
  `Decisions/0008` lines. (Root-level `README.md`/`docker-compose.yml`
  changes were made by the calling task directly and are not duplicated
  here — see repo-root `README.md`.)
- 2026-07-07 — Movement/grip REST approach confirmed by hardware teammate:
  the Jetson-side interface will be an HTTP-adapter microservice wrapping
  NeuraPy (NEURA's Python SDK), to be uploaded to the repo shortly. This
  resolves an earlier doubt (Jetson controller found running NeuraPy with no
  REST API, only a read-only joint-state TCP publisher on `:5005` + a
  localhost MJPEG stream) about whether the existing `HttpMovement`/
  `HttpGrip` clients and `contracts/movement_api.md`/`contracts/grip_api.md`
  were the right shape — they are, and will be aligned to the adapter's real
  routes once it lands. Updated `System/orchestrator.md` ("Teammate-owned
  contracts" section) and `Decisions/0005-mock-first-interface-seam-integration.md`
  (new "Update" consequence bullet). No new files; `README.md` unchanged.
- 2026-07-07 — Hand-eye calibration seam + motor-current grip sensing documented (commits `6994503` "Prep hand-eye calibration seam in the grasp chain", `e0a1b13` "Update grip contract for motor-current sensing"). Extended `System/orchestrator.md`: new "Hand-eye calibration & the grasp chain" section (the `base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp` SE(3) composition, `T_base_cam`/`obj_T_grasp`/`grasp_approach_dist` config fields, mm→m unit conversion via `_load_matrix()`); updated "Config" summary; updated the "Teammate-owned contracts" bullets for `grip_api.md` (now motor-current-based: `grasped`+`current`+`width`) and `movement_api.md` (`/gripper` close must block until stall); updated "Two future VLM roles" item 2 (grip sensor is now analog, not binary, ahead of the deferred VLM check); added a one-line note in the loop diagram's GRASP step. Added `Decisions/0006-eye-to-hand-static-calibration.md` (ADR: eye-to-hand → single static `T_base_cam`, never recomposed per frame; `obj_T_grasp` separates object pose from grasp point; explicit mm/m unit handling; identity defaults are deliberately wrong, not safe). Added `Decisions/0007-grip-motor-current-sensing.md` (ADR: motor current over a binary pad; the end-stop false-positive pitfall and its width-based disambiguation; steady-state read timing; no `loop.py`/Protocol changes needed). Updated `README.md`'s `System/orchestrator.md` line and added the two new ADR lines.
- 2026-07-07 — Orchestrator module documented (commit `3abc923`, "Add orchestrator (disassembly state machine) + integration contracts"). Added `System/orchestrator.md` (loop states, `_grasp_with_retry` rectify logic, the Protocol client seam, config, entry points, teammate-owned `contracts/`, the two not-yet-built VLM seams). Added `Decisions/0005-mock-first-interface-seam-integration.md` (ADR: build/demo the full loop against mocks now, swap real clients behind Protocols with no loop changes, as YOLO tuning/Jetson movement/grip sensor land). Added `SOP/running_orchestrator_dry_run.md` (`python -m orchestrator.dry_run`, running the orchestrator service, running just its tests). Updated `System/architecture.md`: pipeline diagram and service table now show the orchestrator plus grasp-planning (naive placeholder, built) and movement/grip (proposed contracts + real HTTP clients, external endpoints still teammate-owned/in-progress) instead of listing them as pure "future"; test count 81 → 86 (5 new orchestrator loop tests). Updated `README.md` and `SOP/running_services.md` with cross-links to the new docs.
- 2026-07-07 — Documentation initialized. Scanned `perception/`, `pose/`, `damage/`, `tests/`, `docker-compose.yml`, and `.github/workflows/tests.yml` at commit `7cf5211`. Created `System/architecture.md`, `System/integration_points.md`, four ADRs in `Decisions/` (perception-vs-pose containerization, perception model stack, damage fail-safe sort policy, pose contract reuse from KIP `kip-pose-viewer`), and two runbooks in `SOP/` (running the services, running the tests). No `Tasks/active` or `Tasks/archive` entries yet — no PRDs exist in the repo at this point.
