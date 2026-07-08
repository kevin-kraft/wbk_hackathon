"""Grasp planner for slot mode.

The slot's pre-measured base pose IS the grasp (`part.slot_pose`, set by
SlotPerception) — there is no camera->base back-projection to do, because the
coordinate was measured in the base frame directly. This planner just wraps that
pose as a Grasp, standing the pre-grasp off along the approach axis exactly like
NaiveTopDownGrasp, so the downstream approach/grasp/retry machinery is identical.
"""

from __future__ import annotations

from ..config import OrchestratorConfig
from ..models import Grasp, PartDetection, Pose


class SlotGraspPlanner:
    def __init__(self, config: OrchestratorConfig, approach_dist: float | None = None) -> None:
        self.c = config
        self.approach_dist = approach_dist if approach_dist is not None else config.grasp_approach_dist

    @staticmethod
    def _standoff(dz: float):
        import numpy as np

        T = np.eye(4)
        T[2, 3] = dz  # translate along the grasp frame's local z (tool axis)
        return T

    def plan(self, pose: Pose, part: PartDetection) -> Grasp:
        import numpy as np

        if part.slot_pose is None:
            raise ValueError("slot grasp requires part.slot_pose (localization_mode=slots)")
        T_base_grasp = np.array(part.slot_pose, dtype=float)
        pre = T_base_grasp @ self._standoff(-self.approach_dist)  # back off along approach
        return Grasp(
            T_base_grasp=T_base_grasp.tolist(),
            pre_grasp=pre.tolist(),
            width=0.05,
            meta={"planner": "slot", "slot_id": part.id},
        )

    def replan(self, grasp: Grasp, attempt: int) -> Grasp:
        import numpy as np

        # Descend a little further and close a touch more — same rectify behaviour.
        g = np.array(grasp.T_base_grasp, dtype=float) @ self._standoff(0.005 * attempt)
        pre = np.array(grasp.pre_grasp, dtype=float) if grasp.pre_grasp else g
        return Grasp(
            T_base_grasp=g.tolist(),
            pre_grasp=pre.tolist(),
            width=(grasp.width or 0.05) * 0.9,
            meta={**grasp.meta, "attempt": attempt},
        )
