"""Encode captures into the exact wire format the pose stage decodes.

The pose stage (`pose/shared/imaging.py`) decodes with:
  * rgb   -> cv2.imdecode(IMREAD_COLOR) then BGR->RGB   → we must store BGR
  * depth -> cv2.imdecode(IMREAD_UNCHANGED).astype(float)/1000  → 16-bit mm PNG
  * K     -> flat-9 row-major reshaped to 3x3

Keep these two functions byte-compatible with that decoder.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np


def encode_rgb_b64(rgb: np.ndarray) -> str:
    """HxWx3 uint8 RGB -> base64 PNG (stored BGR so the decoder's BGR->RGB restores RGB)."""
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError(f"expected HxWx3 RGB, got shape {rgb.shape}")
    bgr = cv2.cvtColor(np.ascontiguousarray(rgb[:, :, :3]).astype(np.uint8), cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("failed to PNG-encode RGB frame")
    return base64.b64encode(buf.tobytes()).decode()


def encode_depth_mm_b64(depth_mm: np.ndarray, *, max_mm: int = 65535) -> str:
    """HxW depth in millimetres (float, NaN allowed) -> base64 16-bit PNG.

    NaN / inf (no-return pixels, common on a Zivid) become 0, matching the
    "0 = no data" convention the pose stage already tolerates.
    """
    d = np.nan_to_num(depth_mm.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    d = np.clip(np.round(d), 0, max_mm).astype(np.uint16)
    ok, buf = cv2.imencode(".png", d)
    if not ok:
        raise RuntimeError("failed to PNG-encode depth frame")
    return base64.b64encode(buf.tobytes()).decode()
