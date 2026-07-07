"""Decode the pose wire inputs into the numpy arrays the estimators expect.

Depth is uint16 **millimetres** on the wire (matching KIP) and converted to
float32 metres here — both FoundationPose and GigaPose work in metres. Getting
this unit wrong is a known KIP footgun, so it lives in one place.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np


def _decode_bytes(b64: str) -> np.ndarray:
    if b64.strip().startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]
    return np.frombuffer(base64.b64decode(b64), dtype=np.uint8)


def decode_rgb(b64: str) -> np.ndarray:
    """-> HxWx3 uint8 RGB."""
    bgr = cv2.imdecode(_decode_bytes(b64), cv2.IMREAD_COLOR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def decode_depth_m(b64: str) -> np.ndarray:
    """uint16-mm PNG -> HxW float32 metres."""
    raw = cv2.imdecode(_decode_bytes(b64), cv2.IMREAD_UNCHANGED)
    return raw.astype(np.float32) / 1000.0


def decode_mask(b64: str) -> np.ndarray:
    """-> HxW bool."""
    gray = cv2.imdecode(_decode_bytes(b64), cv2.IMREAD_GRAYSCALE)
    return gray > 127


def K_from_flat(k9: list[float]) -> np.ndarray:
    """Flat 9 row-major -> 3x3 float32 intrinsics."""
    return np.asarray(k9, dtype=np.float32).reshape(3, 3)
