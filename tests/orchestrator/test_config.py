"""Hand-eye calibration wiring in OrchestratorConfig."""

from __future__ import annotations

import json

from orchestrator.config import _BASE_CAM_CALIBRATED, OrchestratorConfig

_IDENTITY = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def test_t_base_cam_defaults_to_calibrated(monkeypatch):
    monkeypatch.delenv("T_BASE_CAM", raising=False)
    cfg = OrchestratorConfig()
    assert cfg.T_base_cam == _BASE_CAM_CALIBRATED
    # Translation is stored in METRES (z ~ 1.2 m), not the raw mm from calibration.
    assert abs(cfg.T_base_cam[2][3] - 1.19966) < 1e-9


def test_t_base_cam_env_override_with_mm_units(monkeypatch):
    flat = [1, 0, 0, 100, 0, 1, 0, 200, 0, 0, 1, 300, 0, 0, 0, 1]
    monkeypatch.setenv("T_BASE_CAM", json.dumps(flat))
    monkeypatch.setenv("T_BASE_CAM_UNITS", "mm")
    cfg = OrchestratorConfig()
    assert cfg.T_base_cam[0][3] == 0.1
    assert cfg.T_base_cam[1][3] == 0.2
    assert cfg.T_base_cam[2][3] == 0.3


def test_calibrated_default_is_a_proper_rotation():
    # The 3x3 block should be orthonormal (rows are unit-length, mutually orthogonal).
    R = [row[:3] for row in _BASE_CAM_CALIBRATED[:3]]
    for i in range(3):
        assert abs(sum(c * c for c in R[i]) - 1.0) < 1e-4
    for i in range(3):
        for j in range(i + 1, 3):
            assert abs(sum(R[i][k] * R[j][k] for k in range(3))) < 1e-4


def test_obj_t_grasp_still_defaults_to_identity(monkeypatch):
    monkeypatch.delenv("T_OBJ_GRASP", raising=False)
    cfg = OrchestratorConfig()
    assert cfg.obj_T_grasp == _IDENTITY
