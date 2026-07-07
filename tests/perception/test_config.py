"""services/shared/config.py — env-driven Settings + resolve_device fallback."""

from __future__ import annotations

import importlib
import sys

import pytest

from services.shared import config as config_module
from services.shared.config import Settings, resolve_device


def test_settings_defaults_when_no_env(monkeypatch):
    for var in (
        "PERCEPTION_DEVICE",
        "WEIGHTS_DIR",
        "YOLO_WEIGHTS",
        "SAM3_MODEL_ID",
        "SAM3_WEIGHTS",
        "LOCATE_MODEL_ID",
        "LOCATE_WEIGHTS",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()

    assert settings.device == "cuda"
    assert settings.weights_dir == "/weights"
    assert settings.yolo_weights == "yolo11n.pt"
    assert settings.sam3_model_id == ""
    assert settings.sam3_weights == ""
    assert settings.locate_model_id == ""
    assert settings.locate_weights == ""


def test_settings_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("PERCEPTION_DEVICE", "cpu")
    monkeypatch.setenv("WEIGHTS_DIR", "/custom-weights")
    monkeypatch.setenv("YOLO_WEIGHTS", "custom.pt")
    monkeypatch.setenv("SAM3_MODEL_ID", "facebook/sam3-custom")
    monkeypatch.setenv("SAM3_WEIGHTS", "sam3.ckpt")
    monkeypatch.setenv("LOCATE_MODEL_ID", "nvidia/locate-custom")
    monkeypatch.setenv("LOCATE_WEIGHTS", "locate.ckpt")

    settings = Settings()

    assert settings.device == "cpu"
    assert settings.weights_dir == "/custom-weights"
    assert settings.yolo_weights == "custom.pt"
    assert settings.sam3_model_id == "facebook/sam3-custom"
    assert settings.sam3_weights == "sam3.ckpt"
    assert settings.locate_model_id == "nvidia/locate-custom"
    assert settings.locate_weights == "locate.ckpt"


def test_resolve_device_passes_through_cpu():
    assert resolve_device("cpu") == "cpu"


def test_resolve_device_falls_back_to_cpu_when_torch_missing(monkeypatch):
    # Simulate torch not being importable (the real deployment scenario for
    # these tests: torch is never installed in the light dev env).
    monkeypatch.setitem(sys.modules, "torch", None)

    assert resolve_device("cuda") == "cpu"
    assert resolve_device("cuda:0") == "cpu"


def test_resolve_device_falls_back_to_cpu_when_cuda_unavailable(monkeypatch):
    class _FakeCuda:
        @staticmethod
        def is_available():
            return False

    fake_torch = type("FakeTorch", (), {"cuda": _FakeCuda()})()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert resolve_device("cuda") == "cpu"


def test_resolve_device_keeps_cuda_when_available(monkeypatch):
    class _FakeCuda:
        @staticmethod
        def is_available():
            return True

    fake_torch = type("FakeTorch", (), {"cuda": _FakeCuda()})()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert resolve_device("cuda") == "cuda"


def test_config_module_reimports_cleanly():
    # Sanity check the module itself has no import-time side effects that
    # would break under reimport (defensive: config.py is imported by every
    # service at process start).
    importlib.reload(config_module)
