# Training — custom YOLOv26 detection/segmentation on Isaac-Sim data

## Related Docs
- [Architecture](./architecture.md) — where the trained YOLO weights plug into Stage 1 Perception
- [Integration Points](./integration_points.md) — the perception `POST /infer` contract the trained `yolo` service serves
- [SOP: deploying perception to the GPU server](../SOP/deploy_perception_gpu_server.md) — the container the trained weights get deployed into
- [ADR 0012: mask-derived detection labels over bbox_2d](../Decisions/0012-mask-derived-detection-labels.md) — why `--task detmask` replaced `--task det`
- [ADR 0013: AMP disabled on the Blackwell training stack](../Decisions/0013-amp-disabled-blackwell-training.md)
- `training/README.md` (repo) — the canonical step-by-step runbook (setup → convert → train → deploy commands); this doc covers the *why* and *how it's built*, not a copy of those commands
- Root [`README.md`](../../README.md) "Deployment" §2/§3 — the same pipeline summarized in the hackathon-wide deployment topology

## What this is

`training/` trains custom **YOLOv26** detection and segmentation models for the
18 native disassembly-part classes, on synthetic data rendered by Isaac-Sim
Replicator (SDG), on the shared GPU server (`gpu-server`, 8x RTX PRO 6000
Blackwell). The trained detector replaces the perception stage's stock
`yolo11n.pt` default (see [Architecture](./architecture.md) Stage 1) with a
model that actually knows this project's parts.

This is a repo subsystem, not a deployed service — it produces `.pt` weight
files that get copied into the `wbk-perception` container's `YOLO_WEIGHTS`
mount (see the deploy SOP above), then training is done until the next
retrain.

## Pipeline: SDG renders → YOLO dataset → trained weights → deployed

```
Isaac Replicator (SDG)  ──►  isaac_to_yolo.py  ──►  Ultralytics dataset  ──►  train.py (+ supervisor)  ──►  best.pt  ──►  deploy_yolo_weights.sh  ──►  wbk-perception:YOLO_WEIGHTS
  rgb/bbox_2d/instance/         (det/detmask/seg)      images/ (symlinked)      crash-resumable,                         copies best.pt, recreates
  semantic per frame                                   + labels/ + data.yaml    rolling checkpoints                      the container with the mount
```

## `isaac_to_yolo.py` — SDG → Ultralytics converter

Reads one frame directory's worth of Isaac Replicator output per index `NNNN`
(`rgb_NNNN.png`, `bbox_2d_NNNN.json`, `semantic_NNNN.png`, `instance_NNNN.png`,
`semantic_labels_NNNN.json`; recursively discovered so a dataset root with many
`_chunks/stage_*/` leaves works unmodified) and emits a standard Ultralytics
dataset (`images/{train,val}/`, `labels/{train,val}/`, `data.yaml`).

Three task modes (`--task`):

| Task | Source of boxes | Density | Notes |
|---|---|---|---|
| `det` | `bbox_2d` annotator rows (per-prim, already boxed) | sparse (Isaac under-tags prims) | **retired** — see [ADR 0012](../Decisions/0012-mask-derived-detection-labels.md) |
| `detmask` | tight axis-aligned box around each `instance_*.png` blob | dense (~2.8x more objects than `det`) | **current default for detection** |
| `seg` | polygon (via `cv2.findContours` + `approxPolyDP`) around each instance blob | dense | segmentation training |

Class assignment for `detmask`/`seg` is **instance ∩ semantic majority vote**:
for each instance id in `instance_NNNN.png`, the class is whichever semantic
id is most common under that instance's pixel mask (`Counter(sem[mask]).most_common(1)`)
— there's no direct instance→class file exported by the SDG pipeline, so this
cross-references the two per-pixel maps. `BACKGROUND`/`UNLABELLED` are always
dropped. Class names are the sim's native mesh names, kept verbatim
(deliberate — lets the 6DoF pose stage key meshes off the same class string
later). 18 classes are discovered from the current dataset.

Every image is validated with `cv2.imread` before being emitted (not just a
PIL header check) — Ultralytics loads images with cv2 at train time, and some
SDG renders are truncated/bad-checksum PNGs that pass a PIL header read but
fail a full decode. Any frame that fails decode, or throws for any other
reason during label extraction, is skipped (logged, capped at 10 log lines)
rather than aborting the whole conversion batch.

Images are **symlinked** into the output tree, not copied (`--copy` to
override) — avoids duplicating hundreds of GB. Train/val split is
**deterministic**: `md5(stem)[:8] / 0xFFFFFFFF >= val_frac` decides train vs.
val per frame stem, so re-running the converter (e.g. after adding new source
frames) never reshuffles frames that were already split, and no frame can
straddle both splits.

`clean_dataset.py` is a parallel (64-worker) cv2-validator safety net for
datasets built *before* the converter's inline validation existed — removes
undecodable images + their label files + stale `*.cache` files. Not needed
for datasets converted after the validation was added, kept as a one-off
repair tool.

## `train.py` — Ultralytics wrapper with server defaults

Thin CLI around `ultralytics.YOLO(...).train(...)`. Notable behavior beyond
plain Ultralytics flags:

- **Crash-resumable.** `--resume` loads `<project>/<name>/weights/last.pt`
  (Ultralytics restores optimizer/epoch state from it) instead of starting
  from `--model`'s pretrained weights.
- **Rolling checkpoint window.** `--save-period 1` (every epoch) +
  `--keep-last 5` registers an `on_model_save` callback
  (`_prune_old_epochs`) that deletes all but the newest 5 `epoch{N}.pt` files
  after each save; `best.pt`/`last.pt` are never touched by the prune. Keeps
  disk usage bounded on the near-full server without losing recent recovery
  points.
- **`--amp true|false`.** See [ADR 0013](../Decisions/0013-amp-disabled-blackwell-training.md)
  — `false` is required on this server's Blackwell + torch 2.12 stack.
- **`--extra k=v ...`** (`argparse.REMAINDER`, must be the last flag) —
  pass-through overrides appended verbatim to `model.train(...)`, coerced to
  bool/int/float/str. Lets one-off Ultralytics knobs (`lr0`, `mosaic`, ...) be
  set without editing the script.
- **`--time HOURS`** — hard wall-clock budget; Ultralytics stops at the
  deadline regardless of `--epochs`. Used with `run_probes.sh`'s
  steady-state-seconds-per-epoch estimate to size a training run to a known
  time window.
- Task (`detect`/`segment`) is inferred from a `-seg` suffix on `--model`
  (`yolo26m.pt` vs. `yolo26m-seg.pt`); `--task` only needed to override that.
- `--project` defaults to `/mnt/vss-data/kip/runs` (the network drive), not
  the current directory — the server's root disk is ~97% full (see `env.sh`
  below) and any accidental `cwd`-relative checkpoint write would fail or
  starve it.

`train_supervised.sh` wraps `train.py` in a crash-restart loop: on any
non-zero exit (CUDA hiccup, OOM, SSH-drop-killed process), sleeps
(`RETRY_SLEEP=15s`) and relaunches with `--resume` appended, up to
`MAX_RETRIES=20`. Meant to be run inside `screen` so it also survives the
operator's own SSH session dropping.

`run_probes.sh` runs a short (`PROBE_EPOCHS=4`) detection + segmentation
training pair in parallel on two GPUs, reads the steady-state (median,
dropping epoch-1 warmup) seconds/epoch from each run's `results.csv`, and
computes how many epochs fit a wall-clock budget (`HOURS`, default 4) minus a
fixed overhead margin (`OVERHEAD_S=600`, for scan/warmup/final-val/export).
This is how the `--epochs` values baked into the root `README.md`'s example
commands (81 for detmask, 57 for seg) were derived — not arbitrary.

## `env.sh` and `setup_server.sh` — server environment quirks

The GPU server's root disk (and therefore `/tmp`, `~/.cache`, `~/.config`) is
~97% full. `env.sh` (sourced before any converter/training invocation)
redirects every framework temp/cache dir onto the 3.3TB network drive
(`TMPDIR`, `PIP_CACHE_DIR`, `YOLO_CONFIG_DIR`/`ULTRALYTICS_DIR`,
`MPLCONFIGDIR`, `TORCH_HOME`, `HF_HOME`, `XDG_CACHE_HOME`, all under
`/mnt/vss-data/kip/`) — without it, ultralytics/torch/pip fail with "No space
left on device".

`setup_server.sh` builds the training venv (`/mnt/vss-data/kip/venv/yolo`)
with `--system-site-packages` specifically to **reuse the server's
already-working Blackwell torch** (`2.12.1+cu132`, confirmed CUDA-available)
rather than letting `pip install ultralytics` pull a fresh torch that may not
support sm_120. Only `ultralytics`, `tensorboard`, and — because the inherited
system matplotlib is built against a different numpy than the venv's, which
throws `numpy.core.multiarray failed to import` — `matplotlib`/`pandas`/`scipy`
are installed *into* the venv. Per the gpu-server convention (this server uses
plain venv + pip, not `uv`, unlike this user's other machines).

## Deployment: `deploy_yolo_weights.sh`

Run **on** the GPU server (`ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_yolo_weights.sh'`):

1. Copies `runs/parts_detmask_v1/weights/best.pt` → `/mnt/vss-data/kip/weights/parts_detmask.pt`.
2. Recreates the `wbk-perception` container (`docker rm -f` + `docker run`)
   with the same image (`wbk-perception:blackwell`), ports
   (`127.0.0.1:6767:8001`, `127.0.0.1:6769:8003`), and GPU device
   (`--gpus '"device=1"'`) as the previously running config, plus a new
   `-v /mnt/vss-data/kip/weights:/weights -e YOLO_WEIGHTS=/weights/parts_detmask.pt`.
3. Polls `GET :6767/health` until it reports the new model loaded, and checks
   `GET :6769/health` (locate) too, as a smoke test that the container came
   back up cleanly.

Verification beyond the script: `YOLO(weights).names` should list all 18 part
classes. See [SOP: deploying perception to the GPU server](../SOP/deploy_perception_gpu_server.md)
for the wider container/tunnel picture this script assumes is already in place.

`tensorboard.sh` runs TensorBoard over `/mnt/vss-data/kip/runs` (all runs'
event files) bound to `127.0.0.1:6772` on the server — reachable locally at
`http://localhost:6006` via the `gpu-server` SSH tunnel's `6006→6772`
LocalForward (see the deploy SOP).

## Current results (as of this training pass)

| Model | Task | Data | box mAP50 | mask mAP50 | recall |
|---|---|---|---|---|---|
| `parts_det_v1` (retired) | detection, `--task det` (bbox_2d, sparse) | 7,845 boxes | ~0.64 | — | 0.56 |
| `parts_detmask_v1` (**deployed**) | detection, `--task detmask` (instance masks, dense) | 20,403 boxes | 0.99 | — | 0.99 |
| `parts_seg_v1` | segmentation, `--task seg` | (same instance source) | 0.984 | 0.966 | — |

`parts_detmask_v1/weights/best.pt` is the model currently deployed to
`wbk-perception`'s `yolo` service (`YOLO_WEIGHTS=/weights/parts_detmask.pt`).
See [ADR 0012](../Decisions/0012-mask-derived-detection-labels.md) for why
`detmask` replaced `det` for detection training.
