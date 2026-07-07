"""Placeholder grasp planner.

The grasp-planning module is not owned yet; this is a naive stand-in so the loop
is complete. It applies the exact runtime transform chain the calibration analysis
calls for:

    base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp

i.e. object pose (camera frame, from FoundationPose/GigaPose) -> base frame via the
static hand-eye extrinsic (`config.T_base_cam`) -> grasp offset in the object frame
(`config.obj_T_grasp`). These are proper SE(3) matrix compositions, not
element-wise. The pre-grasp stands off along the grasp's own approach axis (local
-z). What's *naive* here is only the grasp geometry (obj_T_grasp defaults to
identity -> grasp at the object origin); real planning reasons about the gripper
and graspable features. Swap this out when that module lands — the chain stays.
"""

from __future__ import annotations

from ..config import OrchestratorConfig
from ..models import Grasp, PartDetection, Pose


class NaiveTopDownGrasp:
    def __init__(self, config: OrchestratorConfig, approach_dist: float | None = None) -> None:
        self.c = config
        self.approach_dist = approach_dist if approach_dist is not None else config.grasp_approach_dist

    @staticmethod
    def _standoff(dz: float):
        import numpy as np

        T = np.eye(4)
        T[2, 3] = dz  # translate along the frame's local z
        return T

    def plan(self, pose: Pose, part: PartDetection) -> Grasp:
        import numpy as np

        T_base_cam = np.array(self.c.T_base_cam, dtype=float)
        T_cam_obj = np.array(pose.T_cam_obj, dtype=float)
        T_obj_grasp = np.array(self.c.obj_T_grasp, dtype=float)

        T_base_grasp = T_base_cam @ T_cam_obj @ T_obj_grasp
        pre = T_base_grasp @ self._standoff(-self.approach_dist)  # back off along approach
        return Grasp(
            T_base_grasp=T_base_grasp.tolist(),
            pre_grasp=pre.tolist(),
            width=0.05,
            meta={"planner": "naive_topdown"},
        )

    def replan(self, grasp: Grasp, attempt: int) -> Grasp:
        import numpy as np

        # Descend a little further along the approach axis and close a touch more.
        g = np.array(grasp.T_base_grasp, dtype=float) @ self._standoff(0.005 * attempt)
        pre = np.array(grasp.pre_grasp, dtype=float) if grasp.pre_grasp else g
        return Grasp(
            T_base_grasp=g.tolist(),
            pre_grasp=pre.tolist(),
            width=(grasp.width or 0.05) * 0.9,
            meta={"planner": "naive_topdown", "attempt": attempt},
        )
