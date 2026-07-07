"""FoundationPose runner.

Mirrors the KIP `fp-svc` wrapper: build the shared scorer/refiner/GL context and
one `FoundationPose` estimator per object mesh at startup, then `register()` per
instance. RGB-D only — depth is required. The FoundationPose repo itself is
imported from FP_REPO (mounted into the container by the base image), so this
module carries no heavy imports at module load.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np


class FoundationPoseRunner:
    name = "foundationpose"

    def __init__(self) -> None:
        self.fp_repo = os.getenv("FP_REPO", "/workspace/FoundationPose")
        self.mesh_dir = os.getenv("FP_MESH_DIR", "/meshes")
        # class -> mesh filename (.obj, in METRES). Override per object set.
        # e.g. FP_CLASS_MESH='{"housing":"housing.obj","bracket":"bracket.obj"}'
        self.class_mesh: dict[str, str] = json.loads(os.getenv("FP_CLASS_MESH", "{}"))
        self.iterations_default = int(os.getenv("FP_ITERATIONS", "5"))
        self._loaded = False
        self._device = "cuda"
        self._est: dict = {}

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def device(self) -> str:
        return self._device

    @property
    def classes(self) -> list[str]:
        return sorted(self.class_mesh)

    def load(self) -> None:
        sys.path.insert(0, self.fp_repo)
        import nvdiffrast.torch as dr  # noqa: WPS433  (native CUDA ext, from FP_REPO env)
        import trimesh
        from estimater import FoundationPose, PoseRefinePredictor, ScorePredictor

        scorer = ScorePredictor()
        refiner = PoseRefinePredictor()
        glctx = dr.RasterizeCudaContext()  # shared, NOT thread-safe -> serial only

        for cls, mesh_file in self.class_mesh.items():
            mesh = trimesh.load(os.path.join(self.mesh_dir, mesh_file))
            self._est[cls] = FoundationPose(
                model_pts=mesh.vertices.astype(np.float32),
                model_normals=mesh.vertex_normals.astype(np.float32),
                mesh=mesh,
                scorer=scorer,
                refiner=refiner,
                glctx=glctx,
                debug=0,
            )
        self._loaded = True

    def estimate(
        self,
        cls: str,
        K: np.ndarray,
        rgb: np.ndarray,
        depth: np.ndarray,
        mask: np.ndarray,
        iterations: int | None = None,
    ) -> np.ndarray:
        if cls not in self._est:
            raise KeyError(f"No FoundationPose mesh registered for class {cls!r}. "
                           f"Known: {self.classes}")
        est = self._est[cls]
        T = est.register(
            K=K,
            rgb=rgb,
            depth=depth,
            ob_mask=mask,
            iteration=iterations or self.iterations_default,
        )
        return np.asarray(T, dtype=float).reshape(4, 4)
