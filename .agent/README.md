# `.agent/` documentation index

Per-project technical documentation for `wbk-hackerthon` (VLM-guided robotic
disassembly, WBK Hackathon Group, started 2026-07-07). This is an index only —
see [`CHANGELOG.md`](./CHANGELOG.md) for the doc history. Repo-level pitch and
quick-start still live in the top-level [`README.md`](../README.md) and
[`docs/architecture.md`](../docs/architecture.md); the docs below add
implementation-level detail on top of those, not a duplicate of them.

## System — current-state architecture

- [`System/architecture.md`](./System/architecture.md) — pipeline overview, per-stage service map (ports, containers, modules), what's built vs. future, test-suite summary.
- [`System/integration_points.md`](./System/integration_points.md) — the four wire contracts (perception `/infer`, pose `/pose`, damage `/inspect`, orchestrator `/events/run` SSE), the shared model-adapter pattern (`BasePerceptionModel` + `app_factory`), the HF weight cache mount, and the deferred-import convention that keeps tests GPU-free.
- [`System/orchestrator.md`](./System/orchestrator.md) — the disassembly state machine (`orchestrator/`) that ties every stage together: loop states, the Protocol-based client seam (mocks vs. real HTTP), config, the hand-eye calibration + grasp chain, entry points (incl. the `/events/run` SSE live-run endpoint + CORS), teammate-owned contracts (now incl. motor-current grip sensing), and the two not-yet-built VLM roles.
- [`System/dashboard.md`](./System/dashboard.md) — the operator console / live demo UI (`frontend/`, React+Vite+TS+Tailwind): pages, the four-layer runtime endpoint config (localStorage > config.json > VITE_* > localhost), and how it consumes the orchestrator's SSE stream.
- [`System/robot_control.md`](./System/robot_control.md) — the movement stage: Group 2's Jetson bridge (`robot_control/`) to the LARA5/NEURA robot socket server — routers, hover-planning safety gates, calibration, config, auth, deployment; what's not yet wired to the orchestrator.

## Decisions — ADRs (why we chose X over Y)

- [`Decisions/0001-perception-shared-container-pose-split-containers.md`](./Decisions/0001-perception-shared-container-pose-split-containers.md) — perception shares one CUDA container (3 FastAPI apps, no dependency conflict); pose splits into two containers (FoundationPose numpy≥2 vs. GigaPose numpy<2 + xformers/panda3d — hard conflict).
- [`Decisions/0002-perception-model-stack.md`](./Decisions/0002-perception-model-stack.md) — why YOLO + SAM3 + LocateAnything (task-specialized, structured output) superseded an earlier general-VLM (Qwen2.5-VL/Molmo) idea for grounding.
- [`Decisions/0003-damage-failsafe-sort-policy.md`](./Decisions/0003-damage-failsafe-sort-policy.md) — damage bin-sort is hardcoded server-side: only clean `ok` → `ok_bin`; `damaged` AND `uncertain` → `reject_bin` (fail-closed).
- [`Decisions/0004-pose-contract-reuses-kip-pose-viewer.md`](./Decisions/0004-pose-contract-reuses-kip-pose-viewer.md) — the `/pose` wire contract is deliberately identical to the KIP `kip-pose-viewer` reference, so a future gateway can fan out to either estimator interchangeably.
- [`Decisions/0005-mock-first-interface-seam-integration.md`](./Decisions/0005-mock-first-interface-seam-integration.md) — the orchestrator depends only on Protocol interfaces so the full loop runs/demos today against mocks while YOLO tuning, the Jetson movement endpoint, and the grip sensor are still in progress; real clients swap in behind the same seam.
- [`Decisions/0006-eye-to-hand-static-calibration.md`](./Decisions/0006-eye-to-hand-static-calibration.md) — eye-to-hand (ceiling camera) calibration means `T_base_cam` is one static matrix, never recomposed per frame; the grasp chain composes it with `cam_T_obj` and `obj_T_grasp`, with explicit mm→m unit handling.
- [`Decisions/0007-grip-motor-current-sensing.md`](./Decisions/0007-grip-motor-current-sensing.md) — grip sensing moved from a binary pad to motor current (current + width), with the end-stop false-positive pitfall documented; the `GripSensor` Protocol absorbed the change with no loop changes.
- [`Decisions/0008-frontend-separate-static-app.md`](./Decisions/0008-frontend-separate-static-app.md) — the dashboard (`frontend/`) is a separate static app, not fused into the orchestrator: the orchestrator must run headless/CI-testable, the dashboard must be re-pointable per-host; the only coupling is the read-only `/events/run` SSE stream.
- [`Decisions/0009-shared-token-auth.md`](./Decisions/0009-shared-token-auth.md) — optional `WBK_API_TOKEN` bearer token gating every work/robot `POST` endpoint (header or `?token=` for SSE); trusted-LAN anti-spam only, explicit co-tenant/browser caveats and why real auth was rejected.
- [`Decisions/0010-robot-control-integration.md`](./Decisions/0010-robot-control-integration.md) — integrating Group 2's `robot_control/` as the movement stage: cherry-picking the folder, vendoring `RobotCommand`, pinning port `9000`, reusing the shared-token auth pattern; the still-open orchestrator↔movement adapter gap (pose-vector conventions unconfirmed).

## SOP — operational runbooks

- [`SOP/running_services.md`](./SOP/running_services.md) — `docker compose` commands per stage, prerequisites (GPU toolkit, gated SAM3 weights, OpenRouter key), building the two pose GPU base images first, per-object CAD/template assets required.
- [`SOP/running_tests.md`](./SOP/running_tests.md) — `uv sync && uv run pytest`, the per-stage import-root split in `conftest.py`, the deferred-import convention, what's intentionally untested.
- [`SOP/running_orchestrator_dry_run.md`](./SOP/running_orchestrator_dry_run.md) — `python -m orchestrator.dry_run` (full loop, all mocked, no GPU/services/hardware), running the orchestrator as a service (`:8000`, `dry_run=true|false`), running just the orchestrator tests.
- [`SOP/deploy_perception_gpu_server.md`](./SOP/deploy_perception_gpu_server.md) — deploying perception to a remote GPU server: the `ARG BASE_IMAGE` build-arg for Blackwell GPUs, rsync'ing HF weights instead of re-downloading, running bound to `127.0.0.1`, reaching it via an SSH tunnel. **In progress** — image built + weights transferring, not yet running/tunneled; pose deployment not started.

## Tasks

- `Tasks/active/` — no in-flight PRDs yet.
- `Tasks/archive/` — nothing shipped/archived yet.

## Glossary

Not present — no heavy domain jargon beyond terms already defined inline in
the System docs (e.g. `T_cam_obj`, bin-sort policy).
