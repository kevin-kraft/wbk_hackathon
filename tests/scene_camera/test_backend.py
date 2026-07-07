"""Backend selection + mock/file behaviour (no Zivid SDK needed)."""

import numpy as np
import pytest

from scene_camera.backend import (
    FileBackend,
    MockBackend,
    ZividBackend,
    make_backend,
)
from scene_camera.config import Settings


def test_make_backend_selects_by_name():
    assert isinstance(make_backend(Settings(backend="mock")), MockBackend)
    assert isinstance(make_backend(Settings(backend="file")), FileBackend)
    assert isinstance(make_backend(Settings(backend="zivid")), ZividBackend)


def test_make_backend_rejects_unknown():
    with pytest.raises(ValueError):
        make_backend(Settings(backend="nope"))


def test_mock_capture_shapes_and_units():
    cap = MockBackend(Settings(backend="mock")).capture()
    assert cap.rgb.dtype == np.uint8 and cap.rgb.shape[2] == 3
    assert cap.depth_mm is not None and cap.depth_mm.shape == cap.rgb.shape[:2]
    assert cap.depth_mm.min() >= 500.0 and cap.depth_mm.max() <= 1000.0  # mm
    assert len(cap.K) == 9


def test_mock_honours_k_override():
    k = [1.0, 0, 2.0, 0, 3.0, 4.0, 0, 0, 1.0]
    cap = MockBackend(Settings(backend="mock", k_override=k)).capture()
    assert cap.K == k


def test_zivid_backend_not_ready_without_sdk():
    # Importing zivid fails on CI/dev — ready must swallow that, not raise.
    assert ZividBackend(Settings(backend="zivid")).ready is False


def test_file_backend_requires_path():
    with pytest.raises(RuntimeError):
        FileBackend(Settings(backend="file", rgb_path="")).capture()
