"""The wire encodings must stay byte-compatible with pose/shared/imaging.py."""

import base64

import cv2
import numpy as np

from scene_camera.imaging import encode_depth_mm_b64, encode_rgb_b64


def _bytes(b64: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), np.uint8)


def _decode_rgb(b64: str) -> np.ndarray:
    # exactly pose/shared/imaging.decode_rgb
    bgr = cv2.imdecode(_bytes(b64), cv2.IMREAD_COLOR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _decode_depth_m(b64: str) -> np.ndarray:
    # exactly pose/shared/imaging.decode_depth_m
    raw = cv2.imdecode(_bytes(b64), cv2.IMREAD_UNCHANGED)
    return raw.astype(np.float32) / 1000.0


def test_rgb_roundtrip_preserves_colours():
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)
    rgb[..., 0] = 200  # R
    rgb[..., 1] = 100  # G
    rgb[..., 2] = 50   # B
    out = _decode_rgb(encode_rgb_b64(rgb))
    assert out.shape == (8, 8, 3)
    assert np.array_equal(out, rgb)  # PNG is lossless; channel order preserved


def test_depth_roundtrip_mm_to_metres():
    depth_mm = np.array([[0.0, 500.0], [1000.0, 2500.0]], dtype=np.float32)
    out = _decode_depth_m(encode_depth_mm_b64(depth_mm))
    assert np.allclose(out, np.array([[0.0, 0.5], [1.0, 2.5]]), atol=1e-3)


def test_depth_nan_and_inf_become_zero():
    depth_mm = np.array([[np.nan, np.inf], [-np.inf, 800.0]], dtype=np.float32)
    out = _decode_depth_m(encode_depth_mm_b64(depth_mm))
    assert out[0, 0] == 0.0 and out[0, 1] == 0.0 and out[1, 0] == 0.0
    assert abs(out[1, 1] - 0.8) < 1e-3


def test_depth_clamped_to_max():
    depth_mm = np.array([[70000.0]], dtype=np.float32)  # beyond uint16
    out = _decode_depth_m(encode_depth_mm_b64(depth_mm, max_mm=65535))
    assert abs(out[0, 0] - 65.535) < 1e-3


def test_encode_rgb_rejects_bad_shape():
    try:
        encode_rgb_b64(np.zeros((8, 8), dtype=np.uint8))
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-HxWx3 input")
