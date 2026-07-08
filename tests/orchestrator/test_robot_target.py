"""Robot-target selection (real | sim | both) and the parallel-mirror TeeMovement.

Covers the seam that lets the loop drive the real Jetson arm, the simulator, or
both in parallel — see orchestrator/factory.py:_build_robot and
orchestrator/clients/tee_movement.py.
"""

from __future__ import annotations

import pytest

from orchestrator.clients.sim_movement import IsaacSimMovement, SimGrip
from orchestrator.clients.tee_movement import TeeMovement
from orchestrator.config import OrchestratorConfig
from orchestrator.factory import _build_robot


class _RecordingMovement:
    """Minimal MovementClient that logs calls and can be told to raise."""

    def __init__(self, name: str, fail_on: set[str] | None = None) -> None:
        self.name = name
        self.calls: list[tuple] = []
        self.fail_on = fail_on or set()

    def _maybe_fail(self, op: str) -> None:
        if op in self.fail_on:
            raise RuntimeError(f"{self.name}:{op} boom")

    def move_to_pose(self, pose_4x4) -> None:
        self.calls.append(("move_to_pose",))
        self._maybe_fail("move_to_pose")

    def move_named(self, name: str) -> None:
        self.calls.append(("move_named", name))
        self._maybe_fail("move_named")

    def set_gripper(self, closed: bool, width=None) -> None:
        self.calls.append(("set_gripper", closed))
        self._maybe_fail("set_gripper")


# --------------------------------------------------------------------------- #
# _build_robot selection
# --------------------------------------------------------------------------- #

def test_real_target_points_both_clients_at_real_urls():
    cfg = OrchestratorConfig(robot_target="real",
                             movement_url="http://arm:9000", grip_url="http://arm:9001")
    move, grip = _build_robot(cfg, None)
    assert move.base_url == "http://arm:9000"
    assert grip.base_url == "http://arm:9001"


def test_sim_target_uses_the_isaac_adapter_and_assume_grasp_grip():
    cfg = OrchestratorConfig(robot_target="sim", movement_sim_url="http://sim:9000")
    move, grip = _build_robot(cfg, None)
    assert isinstance(move, IsaacSimMovement)
    assert move.base_url == "http://sim:9000"
    # No sim grip endpoint -> assume-grasp SimGrip.
    assert isinstance(grip, SimGrip)


def test_sim_target_uses_http_grip_when_grip_sim_url_set():
    cfg = OrchestratorConfig(robot_target="sim",
                             movement_sim_url="http://sim:9000", grip_sim_url="http://sim:9001")
    _, grip = _build_robot(cfg, None)
    assert not isinstance(grip, SimGrip)
    assert grip.base_url == "http://sim:9001"


def test_both_target_mirrors_the_sim_adapter_with_real_primary_and_real_grip():
    cfg = OrchestratorConfig(robot_target="both",
                             movement_url="http://arm:9000", grip_url="http://arm:9001",
                             movement_sim_url="http://sim:9000")
    move, grip = _build_robot(cfg, None)
    assert isinstance(move, TeeMovement)
    assert move.primary.base_url == "http://arm:9000"        # real arm, authoritative
    assert isinstance(move.mirrors[0], IsaacSimMovement)     # sim mirror via the adapter
    assert move.mirrors[0].base_url == "http://sim:9000"
    # Real gripper stays authoritative in mirror mode.
    assert grip.base_url == "http://arm:9001"


def test_sim_or_both_without_sim_url_raises():
    for target in ("sim", "both"):
        with pytest.raises(ValueError, match="MOVEMENT_SIM_URL"):
            _build_robot(OrchestratorConfig(robot_target=target), None)


def test_unknown_target_raises():
    with pytest.raises(ValueError, match="real|sim|both"):
        _build_robot(OrchestratorConfig(robot_target="hologram"), None)


# --------------------------------------------------------------------------- #
# TeeMovement parallel-mirror semantics
# --------------------------------------------------------------------------- #

def test_tee_fans_every_command_to_all_backends():
    primary = _RecordingMovement("real")
    mirror = _RecordingMovement("sim")
    tee = TeeMovement(primary, [mirror])

    tee.move_to_pose([[1]])
    tee.move_named("home")
    tee.set_gripper(True, 0.04)

    assert primary.calls == [("move_to_pose",), ("move_named", "home"), ("set_gripper", True)]
    assert mirror.calls == primary.calls


def test_tee_primary_error_propagates():
    primary = _RecordingMovement("real", fail_on={"move_named"})
    mirror = _RecordingMovement("sim")
    tee = TeeMovement(primary, [mirror])

    with pytest.raises(RuntimeError, match="real:move_named"):
        tee.move_named("home")


def test_tee_mirror_error_is_swallowed_and_reported_not_raised():
    primary = _RecordingMovement("real")
    mirror = _RecordingMovement("sim", fail_on={"move_named"})
    seen: list[tuple[str, Exception]] = []
    tee = TeeMovement(primary, [mirror], on_mirror_error=lambda k, e: seen.append((k, e)))

    # A sim fault must not break a run that is actually driving the real arm.
    tee.move_named("home")
    assert primary.calls == [("move_named", "home")]
    assert len(seen) == 1 and seen[0][0] == "mirror"
    assert "sim:move_named" in str(seen[0][1])
