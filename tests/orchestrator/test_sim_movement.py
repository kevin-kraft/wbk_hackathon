"""IsaacSimMovement adapter: the command-bus mapping + pose math + SimGrip.

Uses httpx.MockTransport to stand in for the Isaac sim backend so the
submit -> poll -> terminal-status flow is exercised without a live sim.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest

from orchestrator.clients.sim_movement import (
    IsaacSimMovement,
    SimGrip,
    _mat_to_pos_quat,
)
from orchestrator.config import OrchestratorConfig

_IDENTITY = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def _client(capture=None, cmd_status="succeeded", cmd_error=None):
    """A MockTransport httpx client emulating the sim command bus."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/simulation/actions/execute"):
            body = json.loads(request.content)
            if capture is not None:
                capture.append(body)
            return httpx.Response(200, json={"id": "cmd-1", "type": body["type"], "status": "queued"})
        if request.method == "GET" and "/simulation/debug/commands/" in path:
            return httpx.Response(200, json={"id": "cmd-1", "status": cmd_status, "error": cmd_error})
        return httpx.Response(404, json={"error": f"unexpected {request.method} {path}"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _adapter(**kw):
    cfg = OrchestratorConfig(movement_sim_url="http://sim:9000", api_token="")
    return IsaacSimMovement(cfg, http=_client(**kw))


# --------------------------------------------------------------------------- #
# pose math
# --------------------------------------------------------------------------- #

def test_mat_to_pos_quat_identity():
    pos, quat = _mat_to_pos_quat(_IDENTITY)
    assert pos == [0.0, 0.0, 0.0]
    assert quat == pytest.approx([1.0, 0.0, 0.0, 0.0])


def test_mat_to_pos_quat_translation_is_verbatim():
    m = [row[:] for row in _IDENTITY]
    m[0][3], m[1][3], m[2][3] = 0.1, -0.2, 0.35
    pos, _ = _mat_to_pos_quat(m)
    assert pos == pytest.approx([0.1, -0.2, 0.35])


def test_mat_to_pos_quat_90deg_about_z():
    # Rz(90°): x->y, y->-x.
    m = [[0, -1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    _, quat = _mat_to_pos_quat(m)
    h = math.sqrt(0.5)
    assert quat == pytest.approx([h, 0.0, 0.0, h])


def test_mat_to_pos_quat_returns_unit_quaternion():
    m = [[0, 0, 1, 0], [0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 0, 1]]  # Ry(90°)
    _, quat = _mat_to_pos_quat(m)
    assert math.sqrt(sum(c * c for c in quat)) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# command-bus mapping
# --------------------------------------------------------------------------- #

def test_move_to_pose_submits_move_tcp_with_position_and_quat():
    sent: list[dict] = []
    adapter = IsaacSimMovement(
        OrchestratorConfig(movement_sim_url="http://sim:9000", api_token=""),
        http=_client(capture=sent),
    )
    adapter.move_to_pose(_IDENTITY)
    assert len(sent) == 1
    assert sent[0]["type"] == "move_tcp"
    assert sent[0]["params"]["position"] == [0.0, 0.0, 0.0]
    assert sent[0]["params"]["orientation_quat"] == pytest.approx([1.0, 0.0, 0.0, 0.0])
    assert sent[0]["params"]["steps"] == 60


def test_move_named_home_uses_default_tcp_target():
    sent: list[dict] = []
    adapter = IsaacSimMovement(
        OrchestratorConfig(movement_sim_url="http://sim:9000", api_token=""),
        http=_client(capture=sent),
    )
    adapter.move_named("home")
    assert sent[0]["type"] == "move_tcp"
    assert sent[0]["params"]["position"] == [0.40, 0.00, 0.55]
    assert sent[0]["params"]["orientation_quat"] == [0.0, 1.0, 0.0, 0.0]


def test_move_named_unknown_raises_keyerror():
    adapter = _adapter()
    with pytest.raises(KeyError, match="no sim mapping"):
        adapter.move_named("does_not_exist")


def test_set_gripper_maps_to_open_and_close():
    sent: list[dict] = []
    adapter = IsaacSimMovement(
        OrchestratorConfig(movement_sim_url="http://sim:9000", api_token=""),
        http=_client(capture=sent),
    )
    adapter.set_gripper(closed=True)
    adapter.set_gripper(closed=False, width=0.04)
    assert [s["type"] for s in sent] == ["close_gripper", "open_gripper"]


def test_named_poses_env_override(monkeypatch):
    monkeypatch.setenv("SIM_NAMED_POSES", json.dumps({
        "ok_bin": {"type": "move_joint", "params": {"joints": [1, 2, 3, 4, 5, 6, -0.006, 0.006]}}
    }))
    sent: list[dict] = []
    adapter = IsaacSimMovement(
        OrchestratorConfig(movement_sim_url="http://sim:9000", api_token=""),
        http=_client(capture=sent),
    )
    adapter.move_named("ok_bin")
    assert sent[0]["type"] == "move_joint"
    assert sent[0]["params"]["joints"][:6] == [1, 2, 3, 4, 5, 6]
    # Defaults still resolve for names not in the override (mixed types allowed).
    adapter.move_named("home")
    assert sent[1]["type"] == "move_tcp"
    assert sent[1]["params"]["position"] == [0.40, 0.00, 0.55]


# --------------------------------------------------------------------------- #
# command lifecycle: failure + timeout
# --------------------------------------------------------------------------- #

def test_failed_command_raises_runtimeerror():
    adapter = IsaacSimMovement(
        OrchestratorConfig(movement_sim_url="http://sim:9000", api_token=""),
        http=_client(cmd_status="failed", cmd_error="ik_no_solution"),
    )
    with pytest.raises(RuntimeError, match="ik_no_solution"):
        adapter.move_to_pose(_IDENTITY)


def test_command_that_never_finishes_times_out():
    adapter = IsaacSimMovement(
        OrchestratorConfig(movement_sim_url="http://sim:9000", api_token=""),
        http=_client(cmd_status="running"),  # never terminal
    )
    adapter.cmd_timeout_s = 0.0  # trip the deadline on the first poll (no sleep)
    with pytest.raises(TimeoutError, match="Isaac worker running"):
        adapter.move_to_pose(_IDENTITY)


# --------------------------------------------------------------------------- #
# SimGrip
# --------------------------------------------------------------------------- #

def test_sim_grip_assumes_grasp_by_default():
    assert SimGrip(OrchestratorConfig()).is_grasped() is True


def test_sim_grip_can_be_forced_off(monkeypatch):
    monkeypatch.setenv("SIM_GRIP_ALWAYS", "0")
    assert SimGrip(OrchestratorConfig()).is_grasped() is False
