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


def white_balance_grayworld(rgb: np.ndarray) -> np.ndarray:
    """Gray-world white balance — neutralise a global colour cast (the Zivid
    RGB's strong green tint) so captures sit closer to the neutral-lit training
    distribution. Robust variant: per-channel means are taken over non-black,
    non-saturated pixels so no-return black and blown highlights don't skew the
    gains. Returns the input unchanged if there isn't enough mid-tone signal.
    """
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return rgb
    out = rgb[:, :, :3].astype(np.float32)
    lum = out.mean(axis=2)
    mask = (lum > 5) & (lum < 250)  # drop no-return black + near-saturated
    if int(mask.sum()) < 100:
        return rgb
    means = np.array([out[:, :, c][mask].mean() for c in range(3)], dtype=np.float32)
    means = np.clip(means, 1e-3, None)
    gains = float(means.mean()) / means  # equalise channel means to their average
    out *= gains[None, None, :]
    return np.clip(out, 0, 255).astype(np.uint8)


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
