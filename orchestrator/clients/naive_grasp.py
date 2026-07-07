"""Placeholder grasp planner.

The grasp-planning module is not owned yet; this is a naive stand-in so the loop
is complete. It transforms the object pose into the base frame (via the
configured camera->base extrinsics) and offers a top-down-ish grasp at the object
origin with a stand-off pre-grasp. Real planning needs the gripper geometry and
proper approach-direction reasoning — swap this out when that module lands.
"""

from __future__ import annotations

from ..config import OrchestratorConfig
from ..models import Grasp, PartDetection, Pose


class NaiveTopDownGrasp:
    def __init__(self, config: OrchestratorConfig, approach_dist: float = 0.10) -> None:
        self.c = config
        self.approach_dist = approach_dist

    def plan(self, pose: Pose, part: PartDetection) -> Grasp:
        import numpy as np

        T_base_cam = np.array(self.c.T_base_cam, dtype=float)
        T_cam_obj = np.array(pose.T_cam_obj, dtype=float)
        T_base_obj = T_base_cam @ T_cam_obj

        grasp = T_base_obj.copy()
        pre = grasp.copy()
        pre[2, 3] += self.approach_dist  # stand off along base +z
        return Grasp(
            T_base_grasp=grasp.tolist(),
            pre_grasp=pre.tolist(),
            width=0.05,
            meta={"planner": "naive_topdown"},
        )

    def replan(self, grasp: Grasp, attempt: int) -> Grasp:
        import numpy as np

        g = np.array(grasp.T_base_grasp, dtype=float)
        g[2, 3] -= 0.005 * attempt  # descend a little further each retry
        pre = np.array(grasp.pre_grasp, dtype=float) if grasp.pre_grasp else g.copy()
        return Grasp(
            T_base_grasp=g.tolist(),
            pre_grasp=pre.tolist(),
            width=(grasp.width or 0.05) * 0.9,  # close a touch more
            meta={"planner": "naive_topdown", "attempt": attempt},
        )
