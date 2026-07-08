# ADR 0013: AMP disabled on the Blackwell training stack

## Related Docs
- [System: Training](../System/training.md) — `train.py`'s `--amp` flag and `run_probes.sh`, both affected
- [SOP: deploying perception to the GPU server](../SOP/deploy_perception_gpu_server.md) — the same RTX PRO 6000 Blackwell server, in the inference container

## Status
Accepted (2026-07-08).

## Context

`train.py` trains `yolo26m`/`yolo26m-seg` on the shared GPU server's RTX PRO
6000 (Blackwell, sm_120) GPUs, on top of the server's system torch build
(`2.12.1+cu132`). Ultralytics defaults to mixed-precision (AMP) training.

## Decision

Training is run with **AMP disabled** (`--amp false`, i.e. full fp32).

## Why

With AMP autocast enabled, validation throws a `CUDA illegal memory access`
error on this specific stack (RTX PRO 6000 Blackwell + torch 2.12/cu132).
This was found via `run_probes.sh`'s short timing-probe runs before
committing to full-length training jobs. fp32 training on the same hardware
runs cleanly with no correctness or stability issues observed.

## Consequences

- `train.py --amp` defaults to `None` (Ultralytics' own default, which is
  AMP-on) but every documented invocation in `training/README.md`, the root
  `README.md`'s example commands, and `run_probes.sh` explicitly passes
  `--amp false`. Any new training run on this server should do the same
  unless the underlying torch/CUDA stack changes and this is re-verified.
  There is no code-level default flip to `false` — it's a documented
  convention, not enforced by the script.
- Training runs measurably slower / uses more GPU memory than AMP would
  provide, on a shared multi-tenant GPU box — an accepted trade-off since the
  alternative is validation crashing mid-run.
- This is specific to the **training** stack (torch 2.12.1+cu132, system
  site-packages). The perception inference container
  (`wbk-perception:blackwell`, torch 2.8/cu128, see [SOP: deploying
  perception to the GPU server](../SOP/deploy_perception_gpu_server.md)) is a
  different, separately-built image — this ADR does not claim anything about
  AMP/precision behavior there; that hasn't been tested.
