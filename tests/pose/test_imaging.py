"""pose/shared/imaging.py — rgb/depth/mask decode + intrinsics reshape."""

from __future__ import annotations

import base64

import cv2
import numpy as np

from shared.imaging import K_from_flat, decode_depth_m, decode_mask, decode_rgb


def _png_b64(arr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def test_decode_rgb_returns_hxwx3_uint8_rgb():
    # BGR on the cv2 side so we can assert the RGB channel swap happened.
    bgr = np.zeros((4, 6, 3), dtype=np.uint8)
    bgr[:, :, 0] = 10  # B
    bgr[:, :, 1] = 20  # G
    bgr[:, :, 2] = 30  # R

    rgb = decode_rgb(_png_b64(bgr))

    assert rgb.shape == (4, 6, 3)
    assert rgb.dtype == np.uint8
    assert rgb[0, 0].tolist() == [30, 20, 10]  # R, G, B


def test_decode_rgb_strips_data_uri_prefix():
    bgr = np.full((2, 2, 3), 128, dtype=np.uint8)
    prefixed = f"data:image/png;base64,{_png_b64(bgr)}"

    rgb = decode_rgb(prefixed)

    assert rgb.shape == (2, 2, 3)


def test_decode_depth_m_converts_uint16_mm_to_float32_metres():
    depth_mm = np.array([[0, 1000], [1500, 65535]], dtype=np.uint16)

    depth_m = decode_depth_m(_png_b64(depth_mm))

    assert depth_m.dtype == np.float32
    assert np.allclose(depth_m, depth_mm.astype(np.float32) / 1000.0)
    assert depth_m[1, 0] == 1.5


def test_decode_mask_thresholds_above_127():
    gray = np.array([[0, 127, 128, 255]], dtype=np.uint8)

    mask = decode_mask(_png_b64(gray))

    assert mask.dtype == bool
    assert mask.tolist() == [[False, False, True, True]]


def test_K_from_flat_reshapes_9_to_3x3():
    flat = [100.0, 0.0, 320.0, 0.0, 100.0, 240.0, 0.0, 0.0, 1.0]

    K = K_from_flat(flat)

    assert K.shape == (3, 3)
    assert K.dtype == np.float32
    assert K[0, 0] == 100.0
    assert K[0, 2] == 320.0
    assert K[1, 2] == 240.0
    assert K[2, 2] == 1.0
