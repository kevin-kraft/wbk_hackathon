# `.agent/` documentation index

Per-project technical documentation for `wbk-hackerthon` (VLM-guided robotic
disassembly, WBK Hackathon Group, started 2026-07-07). This is an index only —
see [`CHANGELOG.md`](./CHANGELOG.md) for the doc history. Repo-level pitch and
quick-start still live in the top-level [`README.md`](../README.md) and
[`docs/architecture.md`](../docs/architecture.md); the docs below add
implementation-level detail on top of those, not a duplicate of them.

## System — current-state architecture

- [`System/architecture.md`](./System/architecture.md) — pipeline overview, per-stage service map (ports, containers, modules), what's built vs. future (grasp planning + movement), test-suite summary.
- [`System/integration_points.md`](./System/integration_points.md) — the three wire contracts (perception `/infer`, pose `/pose`, damage `/inspect`), the shared model-adapter pattern (`BasePerceptionModel` + `app_factory`), the HF weight cache mount, and the deferred-import convention that keeps tests GPU-free.

## Decisions — ADRs (why we chose X over Y)

- [`Decisions/0001-perception-shared-container-pose-split-containers.md`](./Decisions/0001-perception-shared-container-pose-split-containers.md) — perception shares one CUDA container (3 FastAPI apps, no dependency conflict); pose splits into two containers (FoundationPose numpy≥2 vs. GigaPose numpy<2 + xformers/panda3d — hard conflict).
- [`Decisions/0002-perception-model-stack.md`](./Decisions/0002-perception-model-stack.md) — why YOLO + SAM3 + LocateAnything (task-specialized, structured output) superseded an earlier general-VLM (Qwen2.5-VL/Molmo) idea for grounding.
- [`Decisions/0003-damage-failsafe-sort-policy.md`](./Decisions/0003-damage-failsafe-sort-policy.md) — damage bin-sort is hardcoded server-side: only clean `ok` → `ok_bin`; `damaged` AND `uncertain` → `reject_bin` (fail-closed).
- [`Decisions/0004-pose-contract-reuses-kip-pose-viewer.md`](./Decisions/0004-pose-contract-reuses-kip-pose-viewer.md) — the `/pose` wire contract is deliberately identical to the KIP `kip-pose-viewer` reference, so a future gateway can fan out to either estimator interchangeably.

## SOP — operational runbooks

- [`SOP/running_services.md`](./SOP/running_services.md) — `docker compose` commands per stage, prerequisites (GPU toolkit, gated SAM3 weights, OpenRouter key), building the two pose GPU base images first, per-object CAD/template assets required.
- [`SOP/running_tests.md`](./SOP/running_tests.md) — `uv sync && uv run pytest`, the per-stage import-root split in `conftest.py`, the deferred-import convention, what's intentionally untested.

## Tasks

- `Tasks/active/` — no in-flight PRDs yet.
- `Tasks/archive/` — nothing shipped/archived yet.

## Glossary

Not present — no heavy domain jargon beyond terms already defined inline in
the System docs (e.g. `T_cam_obj`, bin-sort policy).
