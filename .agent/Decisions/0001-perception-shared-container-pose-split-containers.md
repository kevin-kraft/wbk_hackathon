# ADR 0001: Perception shares one container; pose splits into two

## Related Docs
- [Architecture](../System/architecture.md) — per-stage service map
- [Integration Points](../System/integration_points.md) — the model-adapter pattern this containerization choice sits on top of

## Status
Accepted (as scaffolded, 2026-07-07 — commit `82a88f9`).

## Context

The pipeline has two GPU-heavy stages: perception (yolo + sam3 +
locateanything) and 6DoF pose (foundationpose + gigapose). Both stages need to
decide whether their component models live in one container or several.

## Decision

**Perception: one CUDA container, three FastAPI processes under `supervisord`.**
`perception/Dockerfile` builds a single image (`pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`
base) with one consolidated `requirements.txt`; `perception/supervisord.conf`
runs `yolo`, `sam3`, and `locateanything` as three independent `uvicorn`
processes on ports 8001–8003. This works because YOLO (Ultralytics), SAM 3
(`transformers`), and LocateAnything (`transformers`, `trust_remote_code`) all
sit on the same torch/CUDA/transformers stack without version conflicts.

**6DoF pose: two separate containers, each its own GPU base image.**
`foundationpose_svc` and `gigapose_svc` each get their own Dockerfile
(`pose/foundationpose_svc/Dockerfile`, `pose/gigapose_svc/Dockerfile`), each
built `FROM` a pre-built model-specific base image (`foundationpose:blackwell`,
`gigapose:blackwell`) rather than sharing one.

## Why

FoundationPose and GigaPose have **conflicting native dependency stacks** that
cannot co-exist in one Python environment:

- FoundationPose needs `numpy>=2` plus a pybind11 C++ extension for its
  pose-clustering step (compiled against that numpy ABI).
- GigaPose pins `numpy<2` and brings in `xformers`, `panda3d`, and MegaPose —
  none of which are numpy-2-compatible in this stack.

This is a hard, transitive dependency conflict, not a style preference — it is
called out explicitly in the Dockerfile comments (`pose/gigapose_svc/Dockerfile`:
"this is a SEPARATE image from foundationpose:blackwell on purpose — the two
stacks disagree on numpy / xformers / panda3d and cannot co-exist") and in
`pose/README.md` ("Two containers, on purpose").

Perception's three models have no such conflict, so splitting them into three
containers would only add operational overhead (three images to build/deploy,
three sets of GPU memory reservations) with no correctness benefit — hence one
shared container there.

## Consequences

- Perception services are still written as fully independent FastAPI apps
  (own `model.py`/`main.py`/`requirements.txt` per service dir) specifically
  so any one of them **can** be split into its own container later without a
  rewrite — the shared-container choice is an operational convenience, not an
  architectural coupling.
- The two pose estimators are **alternatives**, not a coarse→refine chain —
  each does its own internal coarse→refine — so callers pick one endpoint per
  request rather than composing both. See
  [ADR 0004](./0004-pose-contract-reuses-kip-pose-viewer.md) for how the
  shared wire contract keeps them interchangeable despite living in different
  containers.
- Base GPU images (`foundationpose:blackwell`, `gigapose:blackwell`) must be
  built manually from the model repos before `docker compose up` will work for
  pose — see [SOP: running the services](../SOP/running_services.md).
