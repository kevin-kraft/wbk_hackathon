# `.agent/` documentation index

Per-project technical documentation for `wbk-hackerthon` (VLM-guided robotic
disassembly, WBK Hackathon Group, started 2026-07-07). This is an index only —
see [`CHANGELOG.md`](./CHANGELOG.md) for the doc history. Repo-level pitch and
quick-start still live in the top-level [`README.md`](../README.md) and
[`docs/architecture.md`](../docs/architecture.md); the docs below add
implementation-level detail on top of those, not a duplicate of them.

## System — current-state architecture

- [`System/architecture.md`](./System/architecture.md) — pipeline overview, per-stage service map (ports, containers, modules), the GigaPose CAD-free `pipeline='2d'` mode, the mask-encoding fix, what's built vs. future, test-suite summary.
- [`System/integration_points.md`](./System/integration_points.md) — the four wire contracts (perception `/infer`, pose `/pose` incl. the new `pipeline='2d'`, damage `/inspect`, orchestrator `/events/run` SSE), the shared model-adapter pattern (`BasePerceptionModel` + `app_factory`), the mask-encoding gotcha, the HF weight cache mount, and the deferred-import convention that keeps tests GPU-free.
- [`System/orchestrator.md`](./System/orchestrator.md) — the disassembly state machine (`orchestrator/`) that ties every stage together: fixed mode (perception-driven) vs. plan mode (ERP/LLM-generated plan, see ADR 0011's constrained action vocabulary), robot target selection (real/sim/both, see ADR 0014), the Protocol-based client seam (mocks vs. real HTTP), config, the hand-eye calibration + grasp chain, entry points (`/run`, `/events/run` SSE, `/products`, `/plan`), teammate-owned contracts (now incl. motor-current grip sensing), and the two not-yet-built VLM roles.
- [`System/dashboard.md`](./System/dashboard.md) — the operator console / live demo UI (`frontend/`, React+Vite+TS+Tailwind): pages, the four-layer runtime endpoint config (localStorage > config.json > VITE_* > localhost), the Real/Sim/Both robot-target toggle + sim scene capture UI (`SourceToggle`/`PartSelector`/`SceneView`), the YOLO-Det/YOLO-Seg model picker + manual image upload debug aid on the Perception page, and how it consumes the orchestrator's SSE stream.
- [`System/robot_control.md`](./System/robot_control.md) — the movement stage: Group 2's Jetson bridge (`robot_control/`) to the LARA5/NEURA robot socket server — routers, hover-planning safety gates, calibration, config, auth, deployment; what's not yet wired to the orchestrator.
- [`System/training.md`](./System/training.md) — the custom YOLOv26 detection/segmentation training pipeline (`training/`) on synthetic Isaac-Sim data: the SDG→YOLO converter's three task modes and instance∩semantic class assignment, the crash-resumable trainer + rolling checkpoints, GPU-server env quirks, the weight-deployment scripts (detection + the new `yoloseg` sidecar deploy), and current model results (18 classes, mAP50 0.99 detection / 0.984 segmentation).

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
- [`Decisions/0011-llm-action-selector-constrained-vocabulary.md`](./Decisions/0011-llm-action-selector-constrained-vocabulary.md) — the plan-driven loop's optional LLM command synthesizer is an action *selector* over a small fixed vocabulary (named poses + pose references, never coordinates), deterministically validated before any `MovementClient` call, with a scripted fallback on any violation.
- [`Decisions/0012-mask-derived-detection-labels.md`](./Decisions/0012-mask-derived-detection-labels.md) — YOLO detection training derives boxes from instance masks (`--task detmask`), not the sparse `bbox_2d` annotator; lifted detection from mAP50 0.64/recall 0.56 to 0.99/0.99.
- [`Decisions/0013-amp-disabled-blackwell-training.md`](./Decisions/0013-amp-disabled-blackwell-training.md) — AMP disabled (`--amp false`) on the training stack; autocast triggers a CUDA illegal-memory-access in validation on RTX PRO 6000 Blackwell + torch 2.12.
- [`Decisions/0014-robot-target-real-sim-both.md`](./Decisions/0014-robot-target-real-sim-both.md) — `ROBOT_TARGET=real|sim|both` drives the Isaac Sim digital twin instead of/alongside the real arm; `both` mode mirrors via `TeeMovement` (real primary/authoritative, sim best-effort, mirror faults never fail a real run).
- [`Decisions/0015-yoloseg-sidecar-container-no-rebuild.md`](./Decisions/0015-yoloseg-sidecar-container-no-rebuild.md) — the new `yoloseg` service deploys as a `wbk-yoloseg` sidecar container (mounted source, no rebuild) rather than recreating `wbk-perception`, since the prebuilt image predates the service.
- [`Decisions/0016-gigapose-2d-planar-pose-mode.md`](./Decisions/0016-gigapose-2d-planar-pose-mode.md) — why GigaPose gained a CAD-free, model-free `pipeline='2d'` (mask-derived, KIP-seminar-inspired) plus a graceful startup degrade, given the deployed instance has no CAD templates for this project's parts.

## SOP — operational runbooks

- [`SOP/running_services.md`](./SOP/running_services.md) — `docker compose` commands per stage, prerequisites (GPU toolkit, gated SAM3 weights, OpenRouter key), building the two pose GPU base images first, per-object CAD/template assets required.
- [`SOP/running_tests.md`](./SOP/running_tests.md) — `uv sync && uv run pytest`, the per-stage import-root split in `conftest.py`, the deferred-import convention, what's intentionally untested.
- [`SOP/running_orchestrator_dry_run.md`](./SOP/running_orchestrator_dry_run.md) — `python -m orchestrator.dry_run` (full loop, all mocked, no GPU/services/hardware), running the orchestrator as a service (`:8000`, `dry_run=true|false`), running just the orchestrator tests.
- [`SOP/deploy_perception_gpu_server.md`](./SOP/deploy_perception_gpu_server.md) — deploying perception to a remote GPU server: the `ARG BASE_IMAGE` build-arg for Blackwell GPUs, rsync'ing HF weights instead of re-downloading, running bound to `127.0.0.1`, reaching it via an SSH tunnel, deploying newly-trained YOLO/YOLO-Seg weights, the host-port map gotcha (this project's ports are 6767-6770, not container ports/8001). **Deployed and running** (2026-07-08) — three containers (`wbk-perception`, standalone `wbk-sam3`, standalone `wbk-yoloseg`), tunneled via `ssh gpu-server`.
- [`SOP/deploy_jetson_native.md`](./SOP/deploy_jetson_native.md) — deploying `robot_control` + `scene_camera` to the Jetson via a native venv + `nohup` instead of the documented `docker compose` path (blocked there today by an amd64-only GHCR image and no docker access for the device account); version-pin gotchas, update steps, current limitations.
- [`SOP/deploy_pose_podman.md`](./SOP/deploy_pose_podman.md) — deploying `wbk-gigapose`/`wbk-foundationpose` on the GPU server via **podman** (not docker, unlike perception's sibling deployment): the custom root-managed store, required `WBK_API_TOKEN`, the `podman cp` + restart deploy pattern (`deploy_gigapose_2d.sh`), and the no-CAD-templates (`classes: []`) reality behind the new 2D pipeline.

## Tasks

- `Tasks/active/` — nothing in flight right now.
- [`Tasks/archive/llm_orchestrated_disassembly_plan.md`](./Tasks/archive/llm_orchestrated_disassembly_plan.md) — **shipped 2026-07-08.** ERP part selection + LLM-generated disassembly plan, executed step by step, with an optional LLM synthesizing arm commands from a constrained vocabulary (see ADR 0011); closes on the existing damage-VLM OK/reject sort. All four PRD open questions resolved — see [System: Orchestrator](./System/orchestrator.md) "Plan mode" for the current-state reference.

## Glossary

Not present — no heavy domain jargon beyond terms already defined inline in
the System docs (e.g. `T_cam_obj`, bin-sort policy).
