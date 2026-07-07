"""End-to-end orchestrator loop tests, driven entirely by mocks (no deps beyond
the standard library + the orchestrator package)."""

from __future__ import annotations

from orchestrator import mocks
from orchestrator.config import OrchestratorConfig
from orchestrator.loop import DisassemblyOrchestrator


def _build(grip=None, damaged=None, parts=None):
    return DisassemblyOrchestrator(
        scene_camera=mocks.MockSceneCamera(),
        perception=mocks.MockPerception(parts or ["cover", "bracket", "gear"]),
        pose=mocks.MockPose(),
        grasp=mocks.MockGraspPlanner(),
        movement=mocks.MockMovement(),
        grip=grip or mocks.MockGrip(fail_first=True),
        inspection_camera=mocks.MockInspectionCamera(),
        damage=mocks.MockDamage(damaged if damaged is not None else {"gear"}),
        config=OrchestratorConfig(inspection_angles=2),
    )


def test_full_loop_disassembles_and_sorts_all_parts():
    orch = _build()
    stats = orch.run()
    assert stats["removed"] == 3
    assert stats["ok_bin"] == 2  # cover, bracket
    assert stats["reject_bin"] == 1  # gear (damaged)
    assert stats["skipped"] == 0
    assert any(e.state == "DONE" for e in orch.events)


def test_rectify_retry_fires_on_failed_grip():
    orch = _build(grip=mocks.MockGrip(fail_first=True))
    orch.run()
    states = [e.state for e in orch.events]
    assert "REGRASP" in states  # first grasp failed (sensor=0) -> re-planned
    assert "GRIP" in states  # and then succeeded


def test_damaged_part_goes_to_reject_bin():
    orch = _build(damaged={"cover", "bracket", "gear"})
    stats = orch.run()
    assert stats["reject_bin"] == 3
    assert stats["ok_bin"] == 0


def test_ungraspable_part_is_blacklisted_and_stops_cleanly():
    # Grip never confirms -> part can't be grasped; loop must not spin forever.
    orch = _build(grip=mocks.MockGrip(always_fail=True))
    stats = orch.run()
    assert stats["removed"] == 0
    assert stats["skipped"] == 1
    assert any(e.state == "BLOCKED" for e in orch.events)


def test_run_terminates_within_max_steps():
    orch = _build()
    orch.run()
    assert len(orch.events) < 100  # bounded, no runaway
