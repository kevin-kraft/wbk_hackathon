#!/usr/bin/env python3
"""Remove images Ultralytics can't decode at train time (cv2.imread -> None) and
clear stale label caches. Parallel across cores — the converter now validates
with cv2 up front, so this is a safety net / one-off repair for datasets built
before that fix.

    python clean_dataset.py /mnt/vss-data/kip/datasets/parts_det /mnt/vss-data/kip/datasets/parts_seg
"""
from __future__ import annotations

import glob
import os
import sys
from multiprocessing import Pool

import cv2

cv2.setNumThreads(1)


def _bad(img: str) -> str | None:
    try:
        return None if cv2.imread(img) is not None else img
    except Exception:
        return img


def clean(root: str) -> None:
    imgs = glob.glob(f"{root}/images/train/*.png") + glob.glob(f"{root}/images/val/*.png")
    with Pool(64) as p:
        bad = [b for b in p.map(_bad, imgs, chunksize=16) if b]
    for img in bad:
        try:
            os.remove(img)
        except OSError:
            pass
        split = "train" if f"{os.sep}train{os.sep}" in img else "val"
        lbl = f"{root}/labels/{split}/" + os.path.basename(img)[:-4] + ".txt"
        if os.path.exists(lbl):
            os.remove(lbl)
    for c in glob.glob(f"{root}/labels/*.cache"):
        os.remove(c)
    print(f"{os.path.basename(root)}: checked {len(imgs)}, removed {len(bad)} undecodable, caches cleared",
          flush=True)


if __name__ == "__main__":
    for r in sys.argv[1:]:
        clean(r)
