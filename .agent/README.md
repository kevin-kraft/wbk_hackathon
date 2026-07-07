# `.agent/` documentation index

Per-project technical documentation for `wbk-hackerthon` (VLM-guided robotic
disassembly, WBK Hackathon Group, started 2026-07-07). This is an index only —
see [`CHANGELOG.md`](./CHANGELOG.md) for the doc history. Repo-level pitch and
quick-start still live in the top-level [`README.md`](../README.md) and
[`docs/architecture.md`](../docs/architecture.md); the docs below add
implementation-level detail on top of those, not a duplicate of them.

## System — current-state architecture

- [`System/architecture.md`](./System/architecture.md) — pipeline overview, per-stage service map (ports, containers, modules), what's built vs. future, test-suite summary.
- [`System/integration_points.md`](./System/integration_points.md) — the three wire contracts (perception `/infer`, pose `/pose`, damage `/inspect`), the shared model-adapter pattern (`BasePerceptionModel` + `app_factory`), the HF weight cache mount, and the deferred-import convention that keeps tests GPU-free.
- [`System/orchestrator.md`](./System/orchestrator.md) — the disassembly state machine (`orchestrator/`) that ties every stage together: loop states, the Protocol-based client seam (mocks vs. real HTTP), config, the hand-eye calibration + grasp chain, entry points, teammate-owned contracts (now incl. motor-current grip sensing), and the two not-yet-built VLM roles.

## Decisions — ADRs (why we chose X over Y)

- [`Decisions/0001-perception-shared-container-pose-split-containers.md`](./Decisions/0001-perception-shared-container-pose-split-containers.md) — perception shares one CUDA container (3 FastAPI apps, no dependency conflict); pose splits into two containers (FoundationPose numpy≥2 vs. GigaPose numpy<2 + xformers/panda3d — hard conflict).
- [`Decisions/0002-perception-model-stack.md`](./Decisions/0002-perception-model-stack.md) — why YOLO + SAM3 + LocateAnything (task-specialized, structured output) superseded an earlier general-VLM (Qwen2.5-VL/Molmo) idea for grounding.
- [`Decisions/0003-damage-failsafe-sort-policy.md`](./Decisions/0003-damage-failsafe-sort-policy.md) — damage bin-sort is hardcoded server-side: only clean `ok` → `ok_bin`; `damaged` AND `uncertain` → `reject_bin` (fail-closed).
- [`Decisions/0004-pose-contract-reuses-kip-pose-viewer.md`](./Decisions/0004-pose-contract-reuses-kip-pose-viewer.md) — the `/pose` wire contract is deliberately identical to the KIP `kip-pose-viewer` reference, so a future gateway can fan out to either estimator interchangeably.
- [`Decisions/0005-mock-first-interface-seam-integration.md`](./Decisions/0005-mock-first-interface-seam-integration.md) — the orchestrator depends only on Protocol interfaces so the full loop runs/demos today against mocks while YOLO tuning, the Jetson movement endpoint, and the grip sensor are still in progress; real clients swap in behind the same seam.
- [`Decisions/0006-eye-to-hand-static-calibration.md`](./Decisions/0006-eye-to-hand-static-calibration.md) — eye-to-hand (ceiling camera) calibration means `T_base_cam` is one static matrix, never recomposed per frame; the grasp chain composes it with `cam_T_obj` and `obj_T_grasp`, with explicit mm→m unit handling.
- [`Decisions/0007-grip-motor-current-sensing.md`](./Decisions/0007-grip-motor-current-sensing.md) — grip sensing moved from a binary pad to motor current (current + width), with the end-stop false-positive pitfall documented; the `GripSensor` Protocol absorbed the change with no loop changes.

## SOP — operational runbooks

- [`SOP/running_services.md`](./SOP/running_services.md) — `docker compose` commands per stage, prerequisites (GPU toolkit, gated SAM3 weights, OpenRouter key), building the two pose GPU base images first, per-object CAD/template assets required.
- [`SOP/running_tests.md`](./SOP/running_tests.md) — `uv sync && uv run pytest`, the per-stage import-root split in `conftest.py`, the deferred-import convention, what's intentionally untested.
- [`SOP/running_orchestrator_dry_run.md`](./SOP/running_orchestrator_dry_run.md) — `python -m orchestrator.dry_run` (full loop, all mocked, no GPU/services/hardware), running the orchestrator as a service (`:8000`, `dry_run=true|false`), running just the orchestrator tests.

## Tasks

- `Tasks/active/` — no in-flight PRDs yet.
- `Tasks/archive/` — nothing shipped/archived yet.

## Glossary

Not present — no heavy domain jargon beyond terms already defined inline in
the System docs (e.g. `T_cam_obj`, bin-sort policy).
