"""services/shared/imaging.py — base64 (de)serialization helpers."""

from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from PIL import Image

from services.shared.imaging import decode_image_b64, encode_mask_png_b64, to_numpy


def _png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_decode_image_b64_round_trip_size_and_mode():
    original = Image.new("RGB", (17, 9), color=(10, 20, 30))
    decoded = decode_image_b64(_png_b64(original))

    assert decoded.size == (17, 9)
    assert decoded.mode == "RGB"


def test_decode_image_b64_converts_non_rgb_to_rgb():
    # Grayscale source should still come back as RGB (the contract every
    # downstream numpy/model consumer relies on).
    gray = Image.new("L", (8, 4), color=128)
    decoded = decode_image_b64(_png_b64(gray))

    assert decoded.mode == "RGB"
    assert decoded.size == (8, 4)


def test_decode_image_b64_strips_data_uri_prefix():
    img = Image.new("RGB", (5, 5), color=(255, 0, 0))
    raw_b64 = _png_b64(img)
    prefixed = f"data:image/png;base64,{raw_b64}"

    decoded = decode_image_b64(prefixed)

    assert decoded.size == (5, 5)
    assert to_numpy(decoded)[0, 0].tolist() == [255, 0, 0]


def test_to_numpy_shape_and_dtype():
    img = Image.new("RGB", (6, 3), color=(1, 2, 3))
    arr = to_numpy(img)

    assert arr.shape == (3, 6, 3)
    assert arr.dtype == np.uint8


@pytest.mark.parametrize(
    "mask",
    [
        np.array([[True, False], [False, True]]),
        np.array([[1, 0], [0, 1]], dtype=np.int64),
        np.array([[255, 0], [0, 255]], dtype=np.uint8),
    ],
    ids=["bool", "0-1", "0-255"],
)
def test_encode_mask_png_b64_accepts_bool_01_and_0255(mask):
    encoded = encode_mask_png_b64(mask)
    raw = base64.b64decode(encoded)
    img = Image.open(io.BytesIO(raw))

    assert img.mode == "L"
    arr = np.asarray(img)
    # Wherever the input mask was "truthy" the PNG should be 255, else 0.
    expected = (mask > 0).astype(np.uint8) * 255
    assert np.array_equal(arr, expected)


def test_encode_mask_png_b64_already_uint8_0_255_passthrough():
    mask = np.array([[0, 255], [255, 0]], dtype=np.uint8)
    encoded = encode_mask_png_b64(mask)
    arr = np.asarray(Image.open(io.BytesIO(base64.b64decode(encoded))))

    assert np.array_equal(arr, mask)
