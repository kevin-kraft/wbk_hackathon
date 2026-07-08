"""Image (de)serialization helpers shared by the services."""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image


def decode_image_b64(data: str) -> Image.Image:
    """Decode a base64 (optionally data-URI-prefixed) image into RGB PIL."""
    if data.strip().startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    raw = base64.b64decode(data)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def to_numpy(img: Image.Image) -> np.ndarray:
    """RGB PIL -> HxWx3 uint8 array."""
    return np.asarray(img)


def encode_mask_png_b64(mask: np.ndarray) -> str:
    """Encode a boolean / 0-1 / 0-255 HxW mask as a base64 PNG (mode L, 0/255).

    Always binarizes any-nonzero -> 255. The previous `dtype != uint8` guard left
    a uint8 0/1 mask (what Ultralytics `masks.data` yields) at 0/1, which the
    consumers' `> 127` threshold then read as empty. `(mask > 0) * 255` is
    idempotent for already-0/255 masks, so this is safe for every caller.
    """
    m = (np.asarray(mask) > 0).astype(np.uint8) * 255
    buf = io.BytesIO()
    Image.fromarray(m, mode="L").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
