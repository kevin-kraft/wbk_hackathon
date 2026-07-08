#!/usr/bin/env python3
"""Convert Isaac-Sim (Replicator) synthetic renders into an Ultralytics YOLO dataset.

Source layout (the ``tdg`` / LARA5 SDG pipeline output) — one *frame directory*
holds many frames sharing a numeric index ``NNNN``:

    <frame_dir>/
        rgb_0000.png                 RGB, 2448x2048
        bbox_2d_0000.json            {"data": [[semanticId, x1, y1, x2, y2, occlusion], ...]}
        semantic_0000.png            per-pixel semantic-id map (mode L)
        instance_0000.png            per-pixel instance-id map (mode L)
        semantic_labels_0000.json    {"idToLabels": {"<id>": {"class": "<name>"}}}
        pose_0000.json, obb_2d_*, depth_* ...   (not used here)

Frame directories are discovered recursively, so pointing ``--src`` at a dataset
root (``robot_subset_train/``) with many ``_chunks/stage_*/stage_*/`` leaves picks
up everything.

Two tasks (choose with ``--task``):

* ``det`` — one YOLO box per ``bbox_2d`` row (already per-prim), class from
  ``semantic_labels``. Boxes are axis-aligned pixel xyxy -> normalized xywh.
* ``seg`` — one polygon per *instance*: take each id in ``instance_*.png``, its
  class is the majority ``semantic_*.png`` id under that instance mask (no
  instance->class file is exported by the pipeline, so we cross-reference), then
  the largest external contour -> normalized polygon.

``BACKGROUND`` and ``UNLABELLED`` are always dropped. Class names are the sim's
native mesh names (kept verbatim so downstream 6DoF pose can key meshes off the
class); use ``--include`` to restrict to a subset or ``--class-map`` to merge.

Output (Ultralytics-standard, images symlinked to avoid duplicating ~GBs):

    <out>/
        images/{train,val}/<stem>.png -> symlink to source rgb
        labels/{train,val}/<stem>.txt
        data.yaml

Train/val split is deterministic (hash of stem), so re-runs are stable and the
same frame never straddles the split.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

_DROP = {"BACKGROUND", "UNLABELLED"}
_RGB_RE = re.compile(r"^rgb_(\d+)\.png$")


def log(msg: str) -> None:
    print(msg, flush=True)


def find_frames(src: Path):
    """Yield (frame_dir, index_str) for every rgb_NNNN.png under src."""
    for rgb in sorted(src.rglob("rgb_*.png")):
        m = _RGB_RE.match(rgb.name)
        if m:
            yield rgb.parent, m.group(1)


def load_id2class(frame_dir: Path, idx: str) -> dict[int, str]:
    p = frame_dir / f"semantic_labels_{idx}.json"
    with open(p) as f:
        raw = json.load(f)["idToLabels"]
    return {int(k): v["class"] for k, v in raw.items()}


def stem_for(frame_dir: Path, idx: str, src: Path) -> str:
    """Unique, collision-free stem from the frame's path relative to src."""
    rel = frame_dir.relative_to(src).as_posix().strip("/")
    rel = rel.replace("/", "_") if rel and rel != "." else "root"
    return f"{rel}_{idx}"


def is_train(stem: str, val_frac: float) -> bool:
    h = int(hashlib.md5(stem.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h >= val_frac


def canon(name: str, class_map: dict[str, str]) -> str:
    return class_map.get(name, name)


def collect_classes(src: Path, include: set[str] | None, class_map: dict[str, str]) -> list[str]:
    """Pass 1: union of real class names across all frames (post-remap)."""
    names: set[str] = set()
    for frame_dir, idx in find_frames(src):
        try:
            id2class = load_id2class(frame_dir, idx)
        except FileNotFoundError:
            continue
        for raw in id2class.values():
            if raw in _DROP:
                continue
            c = canon(raw, class_map)
            if include is None or c in include:
                names.add(c)
    return sorted(names)


def det_lines(frame_dir: Path, idx: str, id2class, name2gid, class_map, w: int, h: int) -> list[str]:
    p = frame_dir / f"bbox_2d_{idx}.json"
    with open(p) as f:
        data = json.load(f).get("data", [])
    lines = []
    for row in data:
        sid, x1, y1, x2, y2 = int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4])
        raw = id2class.get(sid)
        if raw is None or raw in _DROP:
            continue
        c = canon(raw, class_map)
        gid = name2gid.get(c)
        if gid is None:
            continue
        x1, x2 = sorted((max(0.0, x1), min(w, x2)))
        y1, y2 = sorted((max(0.0, y1), min(h, y2)))
        bw, bh = x2 - x1, y2 - y1
        if bw < 2 or bh < 2:
            continue
        xc, yc = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        lines.append(f"{gid} {xc:.6f} {yc:.6f} {bw / w:.6f} {bh / h:.6f}")
    return lines


def detmask_lines(frame_dir: Path, idx: str, id2class, name2gid, class_map,
                  min_area: int) -> list[str]:
    """Detection boxes derived from the instance masks (dense) rather than the
    sparse ``bbox_2d`` annotator. Same instance∩semantic majority-vote class
    assignment as ``seg_lines``, but emits each instance's tight axis-aligned
    bounding box. Recovers the ~2.8x more objects the mask pipeline sees."""
    import numpy as np

    inst = np.array(Image.open(frame_dir / f"instance_{idx}.png"))
    sem = np.array(Image.open(frame_dir / f"semantic_{idx}.png"))
    if inst.shape != sem.shape:
        return []
    h, w = inst.shape[:2]
    lines = []
    for iid in np.unique(inst):
        if iid == 0:
            continue
        mask = inst == iid
        if int(mask.sum()) < min_area:
            continue
        sid = int(Counter(sem[mask].tolist()).most_common(1)[0][0])
        raw = id2class.get(sid)
        if raw is None or raw in _DROP:
            continue
        gid = name2gid.get(canon(raw, class_map))
        if gid is None:
            continue
        ys, xs = np.where(mask)
        x1, x2 = int(xs.min()), int(xs.max()) + 1
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        bw, bh = x2 - x1, y2 - y1
        if bw < 2 or bh < 2:
            continue
        xc, yc = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        lines.append(f"{gid} {xc:.6f} {yc:.6f} {bw / w:.6f} {bh / h:.6f}")
    return lines


def seg_lines(frame_dir: Path, idx: str, id2class, name2gid, class_map,
              min_area: int, eps_frac: float) -> list[str]:
    import cv2

    inst = np.array(Image.open(frame_dir / f"instance_{idx}.png"))
    sem = np.array(Image.open(frame_dir / f"semantic_{idx}.png"))
    if inst.shape != sem.shape:
        return []
    h, w = inst.shape[:2]
    lines = []
    for iid in np.unique(inst):
        if iid == 0:
            continue
        mask = inst == iid
        area = int(mask.sum())
        if area < min_area:
            continue
        sids = sem[mask]
        sid = int(Counter(sids.tolist()).most_common(1)[0][0])
        raw = id2class.get(sid)
        if raw is None or raw in _DROP:
            continue
        c = canon(raw, class_map)
        gid = name2gid.get(c)
        if gid is None:
            continue
        m8 = (mask.astype(np.uint8)) * 255
        contours, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        if cv2.contourArea(cnt) < min_area:
            continue
        eps = eps_frac * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(approx) < 3:
            continue
        pts = " ".join(f"{x / w:.6f} {y / h:.6f}" for x, y in approx)
        lines.append(f"{gid} {pts}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, type=Path, help="dataset root containing rgb_*.png frames (recursive)")
    ap.add_argument("--out", required=True, type=Path, help="output YOLO dataset dir")
    ap.add_argument("--task", choices=["det", "seg", "detmask"], default="det",
                    help="det=boxes from bbox_2d; detmask=boxes from instance masks (dense); seg=polygons")
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--include", default="", help="comma list of class names to keep (default: all real classes)")
    ap.add_argument("--class-map", type=Path, default=None, help="JSON {src_name: merged_name} remap")
    ap.add_argument("--min-area", type=int, default=64, help="seg: drop instances smaller than this many px")
    ap.add_argument("--eps-frac", type=float, default=0.004, help="seg: polygon simplification (frac of arc length)")
    ap.add_argument("--copy", action="store_true", help="copy images instead of symlinking")
    ap.add_argument("--limit", type=int, default=0, help="cap number of frames (0 = all; for smoke tests)")
    args = ap.parse_args()

    src = args.src.resolve()
    if not src.exists():
        log(f"ERROR: src not found: {src}")
        return 2
    include = {s.strip() for s in args.include.split(",") if s.strip()} or None
    class_map = json.loads(args.class_map.read_text()) if args.class_map else {}

    log(f"[1/3] scanning classes under {src} ...")
    classes = collect_classes(src, include, class_map)
    if not classes:
        log("ERROR: no real classes found (only BACKGROUND/UNLABELLED?). Check --src / --include.")
        return 3
    name2gid = {c: i for i, c in enumerate(classes)}
    log(f"      {len(classes)} classes: {classes}")

    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (args.out / sub).mkdir(parents=True, exist_ok=True)

    log(f"[2/3] writing {args.task} labels -> {args.out}")
    n_frames = n_train = n_val = n_obj = n_empty = n_bad = 0
    for frame_dir, idx in find_frames(src):
        if args.limit and n_frames >= args.limit:
            break
        rgb = frame_dir / f"rgb_{idx}.png"
        try:
            id2class = load_id2class(frame_dir, idx)
        except FileNotFoundError:
            continue
        # Source renders occasionally contain a truncated/bad-checksum PNG. Some
        # pass PIL's header read but fail a FULL decode — and Ultralytics loads
        # images with cv2 at train time, so validate with cv2.imread (the same
        # loader) to guarantee every emitted frame is trainable. Skip on ANY
        # failure so one bad frame can't abort the batch.
        try:
            import cv2
            bgr = cv2.imread(str(rgb))
            if bgr is None:
                raise ValueError("cv2 could not decode image")
            h, w = bgr.shape[:2]
            if args.task == "det":
                lines = det_lines(frame_dir, idx, id2class, name2gid, class_map, w, h)
            elif args.task == "detmask":
                lines = detmask_lines(frame_dir, idx, id2class, name2gid, class_map, args.min_area)
            else:
                lines = seg_lines(frame_dir, idx, id2class, name2gid, class_map, args.min_area, args.eps_frac)
        except Exception as e:  # noqa: BLE001 - batch converter must not die on one frame
            n_bad += 1
            if n_bad <= 10:
                log(f"      skip corrupt/unreadable frame {rgb}: {type(e).__name__}: {e}")
            continue

        stem = stem_for(frame_dir, idx, src)
        split = "train" if is_train(stem, args.val_frac) else "val"
        img_link = args.out / f"images/{split}/{stem}.png"
        if not img_link.exists():
            if args.copy:
                import shutil
                shutil.copy2(rgb, img_link)
            else:
                img_link.symlink_to(rgb)
        (args.out / f"labels/{split}/{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))

        n_frames += 1
        n_obj += len(lines)
        n_empty += 1 if not lines else 0
        if split == "train":
            n_train += 1
        else:
            n_val += 1
        if n_frames % 250 == 0:
            log(f"      {n_frames} frames ({n_obj} objects) ...")

    data_yaml = args.out / "data.yaml"
    names_block = "\n".join(f"  {i}: {c}" for i, c in enumerate(classes))
    data_yaml.write_text(
        f"# Auto-generated by isaac_to_yolo.py (task={args.task})\n"
        f"path: {args.out.resolve()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {len(classes)}\n"
        f"names:\n{names_block}\n"
    )

    log(f"[3/3] done: {n_frames} frames (train {n_train} / val {n_val}), "
        f"{n_obj} objects, {n_empty} empty frames, {n_bad} corrupt skipped")
    log(f"      data.yaml -> {data_yaml}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
