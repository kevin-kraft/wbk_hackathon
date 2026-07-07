"""Environment-driven configuration shared by all perception services.

Everything is overridable via env vars so the same image runs on a laptop
(PERCEPTION_DEVICE=cpu) or a GPU box (the default) without code changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # "cuda" | "cpu" | "cuda:0" ... resolved against availability at load time.
    device: str = field(default_factory=lambda: os.getenv("PERCEPTION_DEVICE", "cuda"))
    weights_dir: str = field(default_factory=lambda: os.getenv("WEIGHTS_DIR", "/weights"))

    # --- YOLO ---
    yolo_weights: str = field(default_factory=lambda: os.getenv("YOLO_WEIGHTS", "yolo11n.pt"))

    # --- SAM3 --- (model id / checkpoint filled in once the backend is pinned)
    sam3_model_id: str = field(default_factory=lambda: os.getenv("SAM3_MODEL_ID", ""))
    sam3_weights: str = field(default_factory=lambda: os.getenv("SAM3_WEIGHTS", ""))

    # --- LocateAnything ---
    locate_model_id: str = field(default_factory=lambda: os.getenv("LOCATE_MODEL_ID", ""))
    locate_weights: str = field(default_factory=lambda: os.getenv("LOCATE_WEIGHTS", ""))


def resolve_device(preferred: str) -> str:
    """Fall back to CPU if CUDA was requested but is unavailable."""
    if preferred.startswith("cuda"):
        try:
            import torch

            if not torch.cuda.is_available():
                return "cpu"
        except Exception:
            return "cpu"
    return preferred
