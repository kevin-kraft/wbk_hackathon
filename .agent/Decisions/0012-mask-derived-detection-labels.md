# ADR 0012: Mask-derived detection labels (`detmask`) over the `bbox_2d` annotator

## Related Docs
- [System: Training](../System/training.md) — the converter (`isaac_to_yolo.py`) and trainer this decision governs
- [ADR 0002: perception model stack](./0002-perception-model-stack.md) — the YOLO detector this trains weights for

## Status
Accepted (2026-07-08).

## Context

`isaac_to_yolo.py` converts Isaac-Sim Replicator (SDG) output into an
Ultralytics YOLO detection dataset. The first approach (`--task det`) took
boxes straight from the SDG pipeline's `bbox_2d` annotator — one JSON row per
tagged prim, already boxed, seemingly the natural source.

Training `yolo26m` detection on that dataset produced 7,845 boxes across the
converted frames and a detector with **high precision but low recall**
(mAP50 ~0.64, recall 0.56): the model correctly boxed what it found, but
missed a large fraction of parts present in the scene.

## Decision

Derive detection boxes from the **instance segmentation masks** instead
(`--task detmask`): for each blob in `instance_NNNN.png`, take its tight
axis-aligned bounding box, and assign its class by the same
instance∩semantic majority-vote used for `--task seg` (see
[System: Training](../System/training.md)).

## Why

The `bbox_2d` annotator **under-tags prims** — it does not emit a box for
every object instance actually visible and masked in the scene, only a
subset. The instance mask (`instance_NNNN.png`) is dense: every pixel
belongs to some instance id, so deriving boxes from it recovers every object
the renderer actually segmented, not just the ones the `bbox_2d` annotator
happened to tag.

The mask-derived dataset has **~2.8x more objects** (20,403 boxes vs. 7,845)
from the same source frames. Training `parts_detmask_v1` on it lifted
detection to **mAP50 0.99 / recall 0.99** — matching the segmentation
model's quality (0.984 box / 0.966 mask mAP50) trained on the same instance
masks, and confirming the `bbox_2d` sparsity — not the detector architecture
or training recipe — was the bottleneck.

## Consequences

- `--task det` (the `bbox_2d`-sourced path) is **retired** for this
  project's detection training; `--task detmask` is the default recommended
  path in `training/README.md` and the root `README.md`'s quick-start
  commands. The code path for `--task det` (`det_lines()` in
  `isaac_to_yolo.py`) is kept for completeness/comparison, not deleted.
- Detection and segmentation training now derive labels from the **same
  underlying source** (instance masks) via near-identical logic
  (`detmask_lines()` mirrors `seg_lines()` minus the polygon-approximation
  step) — this is why their quality tracks so closely (0.99 vs. 0.984/0.966
  mAP50).
- `parts_detmask_v1/weights/best.pt` is the version deployed to the
  perception `yolo` service (see [SOP: deploying perception to the GPU
  server](../SOP/deploy_perception_gpu_server.md)); `parts_det_v1` is not
  deployed anywhere.
