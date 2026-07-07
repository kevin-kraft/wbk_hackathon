"""app/services/transform.py — pure numpy hand-eye calibration helpers.

umeyama_rigid solves for the rigid transform (R, t) mapping p_world -> q_base;
apply_transform/residuals/absolute_world are used against it in
calibration.py/hover_service.py. All exercised here with known, hand-checked
inputs (no robot, no disk).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.transform import absolute_world, apply_transform, residuals, umeyama_rigid


def test_absolute_world_adds_table_origin():
    result = absolute_world([1.0, 2.0, 3.0], [0.5, -0.5, 0.0])
    assert np.allclose(result, [1.5, 1.5, 3.0])


def test_umeyama_rigid_recovers_pure_translation():
    p_world = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    translation = np.array([0.1, 0.2, 0.3])
    q_base = (np.asarray(p_world) + translation).tolist()

    rotation, t, info = umeyama_rigid(p_world, q_base)

    assert np.allclose(rotation, np.eye(3), atol=1e-8)
    assert np.allclose(t, translation, atol=1e-8)
    assert info["rms"] == pytest.approx(0.0, abs=1e-8)
    assert info["max_err"] == pytest.approx(0.0, abs=1e-8)
    assert info["n"] == 4


def test_umeyama_rigid_recovers_known_rotation_and_translation():
    # 90-degree rotation about Z, plus a translation.
    theta = np.pi / 2
    rot_z = np.array(
        [[np.cos(theta), -np.sin(theta), 0.0], [np.sin(theta), np.cos(theta), 0.0], [0.0, 0.0, 1.0]]
    )
    translation = np.array([1.0, -1.0, 0.5])
    p_world = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    q_base = (p_world @ rot_z.T) + translation

    rotation, t, info = umeyama_rigid(p_world, q_base)

    assert np.allclose(rotation, rot_z, atol=1e-8)
    assert np.allclose(t, translation, atol=1e-8)
    assert info["rms"] == pytest.approx(0.0, abs=1e-8)


def test_umeyama_rigid_requires_at_least_three_points():
    with pytest.raises(ValueError):
        umeyama_rigid([[0, 0, 0], [1, 0, 0]], [[0, 0, 0], [1, 0, 0]])


def test_umeyama_rigid_requires_matching_shapes():
    with pytest.raises(ValueError):
        umeyama_rigid([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 0, 0], [1, 0, 0]])


def test_apply_transform_matches_forward_model():
    rotation = np.eye(3)
    translation = [1.0, 2.0, 3.0]
    result = apply_transform(rotation, translation, [0.0, 0.0, 0.0])
    assert np.allclose(result, translation)


def test_residuals_zero_for_exact_fit():
    rotation = np.eye(3)
    translation = [0.0, 0.0, 0.0]
    p_world = [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]
    q_base = [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]
    err = residuals(rotation, translation, p_world, q_base)
    assert np.allclose(err, [0.0, 0.0])


def test_residuals_nonzero_for_mismatched_points():
    rotation = np.eye(3)
    translation = [0.0, 0.0, 0.0]
    p_world = [[0.0, 0.0, 0.0]]
    q_base = [[1.0, 0.0, 0.0]]
    err = residuals(rotation, translation, p_world, q_base)
    assert err[0] == pytest.approx(1.0)
