from __future__ import annotations

import datetime
import json
from pathlib import Path

import numpy as np

from app import env
from app.services.transform import residuals, umeyama_rigid


def add_correspondence(session: dict | None, p_world, q_base, meta=None) -> dict:
    if session is None:
        session = {"points": [], "created": _now()}
    session.setdefault("points", []).append(
        {
            "p_world": [float(v) for v in np.asarray(p_world, float).reshape(3)],
            "q_base": [float(v) for v in np.asarray(q_base, float).reshape(3)],
            "meta": meta or {},
        }
    )
    return session


def solve_calibration(session: dict, tool_down_rpy=None) -> dict:
    points = session["points"]
    if len(points) < env.CALIB_MIN_POINTS:
        raise ValueError(f"need >= {env.CALIB_MIN_POINTS} points, have {len(points)}")

    p_world = np.array([p["p_world"] for p in points], float)
    q_base = np.array([p["q_base"] for p in points], float)
    rotation, translation, info = umeyama_rigid(p_world, q_base)

    leave_one_out = []
    if len(points) > env.CALIB_MIN_POINTS:
        for i in range(len(points)):
            mask = np.arange(len(points)) != i
            r_loo, t_loo, _ = umeyama_rigid(p_world[mask], q_base[mask])
            leave_one_out.append(float(residuals(r_loo, t_loo, p_world[i], q_base[i])[0]))

    lo = q_base.min(axis=0) - env.WORKSPACE_BASE_MARGIN_M
    hi = q_base.max(axis=0) + env.WORKSPACE_BASE_MARGIN_M

    return {
        "R_base_world": rotation.reshape(-1).tolist(),
        "t_base_world": translation.tolist(),
        "table_origin": session.get("table_origin"),
        "residual_rms_m": info["rms"],
        "residual_max_m": info["max_err"],
        "per_point_err_m": info["per_point_err"],
        "leave_one_out_err_m": leave_one_out,
        "n_points": info["n"],
        "tool_down_rpy": list(tool_down_rpy) if tool_down_rpy is not None else None,
        "workspace_base_box": {"lo": lo.tolist(), "hi": hi.tolist()},
        "points": points,
        "created": _now(),
    }


def validate_calibration(calibration: dict) -> None:
    rms = calibration["residual_rms_m"]
    max_err = calibration["residual_max_m"]
    if rms >= env.CALIB_RMS_MAX_M or max_err >= env.CALIB_MAX_ERR_M:
        raise ValueError(
            f"calibration rejected: rms={rms * 1000:.1f}mm "
            f"(<{env.CALIB_RMS_MAX_M * 1000:.0f}), "
            f"max={max_err * 1000:.1f}mm (<{env.CALIB_MAX_ERR_M * 1000:.0f})"
        )


def in_workspace_base_box(calibration: dict, xyz) -> bool:
    box = calibration["workspace_base_box"]
    lo = np.array(box["lo"], float)
    hi = np.array(box["hi"], float)
    point = np.asarray(xyz, float).reshape(3)
    return bool(np.all(point >= lo) and np.all(point <= hi))


def load_session(path: Path | None = None) -> dict:
    return _read_json(path or env.CALIBRATION_SESSION_PATH)


def save_session(session: dict, path: Path | None = None) -> None:
    _write_json(path or env.CALIBRATION_SESSION_PATH, session)


def load_calibration(path: Path | None = None) -> dict:
    calibration = _read_json(path or env.CALIBRATION_PATH)
    rotation = np.array(calibration["R_base_world"], float).reshape(3, 3)
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-6):
        raise ValueError("stored R_base_world is not orthonormal")
    return calibration


def save_calibration(calibration: dict, path: Path | None = None) -> None:
    _write_json(path or env.CALIBRATION_PATH, calibration)


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _write_json(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")
