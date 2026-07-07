from __future__ import annotations

import numpy as np


def absolute_world(t_world, table_origin) -> np.ndarray:
    return np.asarray(t_world, float).reshape(3) + np.asarray(table_origin, float).reshape(3)


def umeyama_rigid(p_world, q_base):
    p = np.asarray(p_world, float).reshape(-1, 3)
    q = np.asarray(q_base, float).reshape(-1, 3)
    if p.shape != q.shape or p.shape[0] < 3:
        raise ValueError("need >=3 matched 3D point pairs")

    p_bar = p.mean(axis=0)
    q_bar = q.mean(axis=0)
    x = p - p_bar
    y = q - q_bar

    h = x.T @ y
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rotation_guard = np.diag([1.0, 1.0, d])
    r = vt.T @ rotation_guard @ u.T
    t = q_bar - r @ p_bar

    err = np.linalg.norm((p @ r.T + t) - q, axis=1)
    info = {
        "rms": float(np.sqrt(np.mean(err ** 2))),
        "max_err": float(err.max()),
        "per_point_err": err.tolist(),
        "n": int(p.shape[0]),
    }
    return r, t, info


def apply_transform(rotation, translation, p_world) -> np.ndarray:
    r = np.asarray(rotation, float).reshape(3, 3)
    t = np.asarray(translation, float).reshape(3)
    return r @ np.asarray(p_world, float).reshape(3) + t


def residuals(rotation, translation, p_world, q_base) -> np.ndarray:
    p = np.asarray(p_world, float).reshape(-1, 3)
    q = np.asarray(q_base, float).reshape(-1, 3)
    return np.linalg.norm((p @ np.asarray(rotation, float).T + translation) - q, axis=1)
