"""GigaPose runner.

Wraps the KIP in-repo adapter `gigapose_infer.GigaPoseInfer`, which bypasses
GigaPose's hydra/BOP batch flow and exposes a single `estimate()` call:
coarse (DINOv2 template match) -> MegaPose refiner -> optional Kabsch/ICP tail.

Depth is OPTIONAL: only the 'rgbd' pipeline uses it (for the Kabsch depth-align
step). Pre-rendered templates for each object must already exist on disk before
this loads (mounted from the GigaPose repo). The adapter builds on CPU first,
forks its render workers, THEN moves to CUDA — do not reorder.
"""

from __future__ import annotations

import os
import sys

import numpy as np


class GigaPoseRunner:
    name = "gigapose"

    def __init__(self) -> None:
        self.gp_repo = os.getenv("GIGAPOSE_REPO", "/workspace/GigaPose")
        self.dataset_name = os.getenv("GP_DATASET", "kip2")
        self.enable_refiner = os.getenv("GP_ENABLE_REFINER", "1") == "1"
        self._loaded = False
        self._device = "cuda"
        self._infer = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def device(self) -> str:
        return self._device

    @property
    def classes(self) -> list[str]:
        # Class->objId map lives inside the adapter; surface it if exposed.
        mapping = getattr(self._infer, "class_to_obj", None) if self._infer else None
        return sorted(mapping) if isinstance(mapping, dict) else []

    def load(self) -> None:
        sys.path.insert(0, self.gp_repo)
        os.environ.setdefault("GP_REFINER_RENDERER", "single")  # headless-safe renderer
        from gigapose_infer import GigaPoseInfer

        self._infer = GigaPoseInfer(
            dataset_name=self.dataset_name,
            enable_refiner=self.enable_refiner,
        )
        self._loaded = True

    def estimate(
        self,
        cls: str,
        K: np.ndarray,
        rgb: np.ndarray,
        mask: np.ndarray,
        depth: np.ndarray | None,
        iterations: int,
        hypotheses: int,
        kabsch: bool,
    ) -> tuple[np.ndarray, float, str]:
        T, score, stage = self._infer.estimate(
            class_name=cls,
            K=K,
            rgb=rgb,
            mask=mask,
            depth=depth,
            iterations=iterations,
            hypotheses=hypotheses,
            kabsch=kabsch,
        )
        return np.asarray(T, dtype=float).reshape(4, 4), float(score), str(stage)
