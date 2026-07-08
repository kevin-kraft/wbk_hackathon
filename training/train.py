#!/usr/bin/env python3
"""Train a YOLOv26 detector or segmenter on the converted Isaac dataset.

Thin Ultralytics wrapper with hackathon-server defaults baked in:

* model  — ``yolo26m.pt`` (det) or ``yolo26m-seg.pt`` (seg); task inferred from
  the ``-seg`` suffix, so ``--task`` only needs overriding for exotic cases.
* device — pin to a specific GPU index (the RTX PRO 6000 box is shared; check
  ``nvidia-smi`` and pick an idle one, e.g. ``--device 0``).
* project — defaults under the network drive so checkpoints don't hit the
  97%-full root disk.

The produced weights land at ``<project>/<name>/weights/best.pt`` — point the
perception YOLO service's ``YOLO_WEIGHTS`` env at that file to deploy.

Example:
    python train.py --data /mnt/vss-data/kip/datasets/parts_det/data.yaml \
        --model yolo26m.pt --epochs 100 --imgsz 1280 --batch 16 --device 0 \
        --name parts_det_v1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="path to data.yaml from isaac_to_yolo.py")
    ap.add_argument("--model", default="yolo26m.pt", help="pretrained weights / model yaml (use *-seg.pt for segmentation)")
    ap.add_argument("--task", default=None, choices=[None, "detect", "segment"], help="override auto-detected task")
    ap.add_argument("--epochs", type=int, default=1000, help="upper bound; --time caps wall-clock and usually stops first")
    ap.add_argument("--time", type=float, default=None, help="hard wall-clock budget in HOURS (overrides epoch count)")
    ap.add_argument("--imgsz", type=int, default=1280, help="source is 2448x2048; parts are small, so default high")
    ap.add_argument("--batch", type=int, default=16, help="-1 for Ultralytics auto-batch")
    ap.add_argument("--device", default="0", help="GPU index (shared box: pick an idle one) or 'cpu'")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--project", default="/mnt/vss-data/kip/runs", help="runs dir (keep off the root disk)")
    ap.add_argument("--name", default="parts", help="run name -> <project>/<name>/")
    ap.add_argument("--patience", type=int, default=30, help="early-stop patience (epochs)")
    ap.add_argument("--amp", default=None, choices=["true", "false"],
                    help="mixed precision; set 'false' if the Blackwell stack throws CUDA illegal-access in val")
    ap.add_argument("--cache", default="False", help="'ram'|'disk'|'False' — do NOT ram-cache the big 300GB set")
    ap.add_argument("--save-period", type=int, default=1,
                    help="checkpoint every N epochs as epoch{N}.pt (1 = every epoch; last.pt is always saved too)")
    ap.add_argument("--keep-last", type=int, default=5,
                    help="rolling window: keep only the newest N epoch*.pt (best.pt + last.pt are never pruned)")
    ap.add_argument("--resume", action="store_true",
                    help="resume from <project>/<name>/weights/last.pt after a crash")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[],
                    help="pass-through key=value overrides appended verbatim, e.g. --extra lr0=0.001 mosaic=0.5")
    args = ap.parse_args()

    if not Path(args.data).exists():
        print(f"ERROR: data.yaml not found: {args.data}", flush=True)
        return 2

    from ultralytics import YOLO

    def _coerce(v: str) -> object:
        s = v.strip()
        if s.lower() in ("true", "false"):
            return s.lower() == "true"
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            return s

    overrides: dict[str, object] = {}
    for kv in args.extra:
        if "=" in kv:
            k, v = kv.split("=", 1)
            overrides[k.strip()] = _coerce(v)
    if args.amp is not None:
        overrides["amp"] = args.amp == "true"

    cache = args.cache
    cache_val: object = cache
    if isinstance(cache, str) and cache.lower() in ("false", "0", "none"):
        cache_val = False

    # Resume from last.pt (survives crashes): load the run's last checkpoint and
    # let Ultralytics restore optimizer/epoch state.
    if args.resume:
        last = Path(args.model) if args.model.endswith("last.pt") \
            else Path(args.project) / args.name / "weights" / "last.pt"
        if not last.exists():
            print(f"ERROR: --resume but no checkpoint at {last}", flush=True)
            return 2
        print(f"[train] resuming from {last}", flush=True)
        model = YOLO(str(last))
    else:
        model = YOLO(args.model)
    if args.task:
        model.task = args.task

    # Rolling window of the last N epoch checkpoints. Ultralytics saves
    # epoch{N}.pt every --save-period epochs but never prunes them; this callback
    # deletes all but the newest --keep-last, leaving best.pt / last.pt intact.
    if args.keep_last and args.keep_last > 0:
        import glob
        import os
        import re as _re

        def _prune_old_epochs(trainer):
            try:
                wdir = str(trainer.wdir)
            except Exception:
                return
            found = []
            for p in glob.glob(os.path.join(wdir, "epoch*.pt")):
                m = _re.search(r"epoch(\d+)\.pt$", p)
                if m:
                    found.append((int(m.group(1)), p))
            found.sort()
            for _, p in found[:-args.keep_last]:
                try:
                    os.remove(p)
                except OSError:
                    pass

        model.add_callback("on_model_save", _prune_old_epochs)

    print(f"[train] model={args.model} data={args.data} device={args.device} "
          f"imgsz={args.imgsz} batch={args.batch} epochs={args.epochs}", flush=True)

    if args.time:
        overrides["time"] = args.time  # hours; Ultralytics stops at the deadline

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project=args.project,
        name=args.name,
        patience=args.patience,
        cache=cache_val,
        save=True,
        save_period=args.save_period,
        resume=args.resume,
        exist_ok=True,
        **overrides,
    )
    save_dir = getattr(results, "save_dir", f"{args.project}/{args.name}")
    print(f"[train] done -> {save_dir}", flush=True)
    print(f"[train] best weights -> {save_dir}/weights/best.pt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
