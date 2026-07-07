"""FastAPI wiring for robot_control (app/main.py).

/health is always open. Every router (commands, joint_states, robot_commands,
robot_workflows) is mounted with `Depends(require_token)`, so any route behind
them is closed exactly like the other services once WBK_API_TOKEN is set. We
exercise this through GET /robot/calibration (robot_workflows router) and
monkeypatch the calibration service so the test never touches disk or the
robot socket.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as robot_control_main
from app.services import calibration

client = TestClient(robot_control_main.app)
TOKEN = "s3cret-token"

_CANNED_CALIBRATION = {
    "R_base_world": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
    "t_base_world": [0.0, 0.0, 0.0],
    "tool_down_rpy": [0.0, 0.0, 0.0],
    "residual_rms_m": 0.001,
    "residual_max_m": 0.002,
}


def test_health_open_even_with_token_set(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    assert client.get("/health").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


def test_health_open_when_token_unset(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    assert client.get("/health").status_code == 200


def test_calibration_open_when_token_unset(monkeypatch):
    monkeypatch.delenv("WBK_API_TOKEN", raising=False)
    monkeypatch.setattr(calibration, "load_calibration", lambda: _CANNED_CALIBRATION)
    assert client.get("/robot/calibration").status_code == 200


def test_calibration_rejects_without_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    monkeypatch.setattr(calibration, "load_calibration", lambda: _CANNED_CALIBRATION)
    assert client.get("/robot/calibration").status_code == 401


def test_calibration_accepts_correct_bearer(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    monkeypatch.setattr(calibration, "load_calibration", lambda: _CANNED_CALIBRATION)
    r = client.get("/robot/calibration", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert r.json() == _CANNED_CALIBRATION


def test_calibration_rejects_wrong_bearer(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    monkeypatch.setattr(calibration, "load_calibration", lambda: _CANNED_CALIBRATION)
    r = client.get("/robot/calibration", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_calibration_accepts_query_token(monkeypatch):
    monkeypatch.setenv("WBK_API_TOKEN", TOKEN)
    monkeypatch.setattr(calibration, "load_calibration", lambda: _CANNED_CALIBRATION)
    r = client.get(f"/robot/calibration?token={TOKEN}")
    assert r.status_code == 200
