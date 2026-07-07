"""End-to-end dry run of the disassembly loop with every stage mocked.

    python -m orchestrator.dry_run        (from the repo root)

No services, weights, GPU, or hardware required — proves the integration and
serves as the demo narration while YOLO / the Jetson endpoint / the grip sensor
are still being built.
"""

from __future__ import annotations

from . import mocks
from .config import OrchestratorConfig
from .loop import DisassemblyOrchestrator
from .models import LoopEvent


def _print_event(event: LoopEvent) -> None:
    print(f"[{event.step:>2}] {event.state:<8} {event.message}")


def main() -> None:
    orchestrator = DisassemblyOrchestrator(
        scene_camera=mocks.MockSceneCamera(),
        perception=mocks.MockPerception(["cover", "bracket", "gear"]),
        pose=mocks.MockPose(),
        grasp=mocks.MockGraspPlanner(),
        movement=mocks.MockMovement(),
        grip=mocks.MockGrip(fail_first=True),  # first grasp fails -> exercises rectify
        inspection_camera=mocks.MockInspectionCamera(),
        damage=mocks.MockDamage(damaged_classes={"gear"}),  # gear -> reject bin
        config=OrchestratorConfig(inspection_angles=2),
        on_event=_print_event,
    )

    print("=== disassembly dry-run (all hardware mocked) ===")
    stats = orchestrator.run()
    print(f"=== summary: {stats} ===")


if __name__ == "__main__":
    main()
