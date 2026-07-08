"""Slot-localization perception + a no-op pose stage.

Drop-in replacements for HttpPerception / HttpPose that satisfy the same
Protocols (clients/base.py), so the orchestrator state machine (loop._process_part)
runs unchanged — the factory just swaps these in when localization_mode="slots".

Instead of "what is the pose of this part", the question becomes "which tray slot
is filled". Occupancy comes from SAM3 (or YOLO-Seg) masks tested against the
calibrated slot centres (slots.compute_occupancy); the grasp coordinate is the
filled slot's pre-measured base pose, carried on PartDetection.slot_pose and
consumed by SlotGraspPlanner. No depth, no intrinsics, no 6DoF.
"""

from __future__ import annotations

from ..config import OrchestratorConfig
from ..models import Box, PartDetection, Pose, SceneFrame
from ..slots import SlotLayout, SlotStatus, compute_occupancy, decode_mask, load_slot_layout


def _identity4x4() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class SlotPerception:
    """Perception client backed by a calibrated tray layout.

    `next_part` / `locate` return the next filled slot (carrying its base pose);
    `is_present` re-checks a specific slot's occupancy after a lift.
    """

    def __init__(self, config: OrchestratorConfig, perception, layout: SlotLayout | None = None) -> None:
        self.c = config
        self.perception = perception  # an HttpPerception (mask source)
        self.layout = layout or load_slot_layout(config.slot_layout_path)
        self.mask_source = (config.slot_mask_source or self.layout.mask_source or "sam3").lower()

    # ------------------------------------------------------------------ #
    def occupancy(self, frame: SceneFrame) -> list[SlotStatus]:
        """Run the configured mask source and score every slot's occupancy."""
        masks: list[tuple[str, object]] = []
        if self.mask_source == "yoloseg":
            for label, b64 in self.perception.segment_labeled(frame):
                masks.append((label, decode_mask(b64)))
        else:
            for cls in self.layout.classes:
                for b64 in self.perception.segment_all(frame, cls):
                    masks.append((cls, decode_mask(b64)))
        return compute_occupancy(masks, self.layout)

    def _detection(self, status: SlotStatus) -> PartDetection:
        u, v = status.pixel
        r = self.layout.radius_px
        return PartDetection(
            class_name=status.expected_class,
            score=status.fill_score,
            box=Box(x1=u - r, y1=v - r, x2=u + r, y2=v + r),
            point=(u, v),
            id=status.slot_id,
            slot_pose=status.base_pose,
        )

    # ------------------------------------------------------------------ #
    def next_part(self, frame: SceneFrame) -> PartDetection | None:
        for status in self.occupancy(frame):
            if status.filled:
                return self._detection(status)
        return None

    def locate(self, frame: SceneFrame, class_name: str) -> PartDetection | None:
        for status in self.occupancy(frame):
            if status.filled and status.expected_class == class_name:
                return self._detection(status)
        return None

    def segment(self, frame: SceneFrame, part: PartDetection) -> str | None:
        # A concrete mask for the located part (before/after overlays); the grasp
        # itself uses the slot pose, not this mask. Reuse the single-mask SAM3 call.
        return self.perception.segment(frame, part)

    def is_present(self, frame: SceneFrame, part: PartDetection) -> bool:
        # "Still present" == the part's slot is still occupied after the lift.
        for status in self.occupancy(frame):
            if status.slot_id == part.id:
                return status.filled
        # Slot id not found (unexpected) — fall back to a class presence check.
        return any(s.filled and s.expected_class == part.class_name for s in self.occupancy(frame))


class SlotPose:
    """No-op pose stage for slot mode: the grasp comes from the slot's base pose,
    so there is nothing to estimate. Returns an identity pose tagged 'slot-lookup'
    to keep the loop's POSE event honest."""

    def estimate(self, frame: SceneFrame, part: PartDetection) -> Pose:
        return Pose(T_cam_obj=_identity4x4(), score=part.score, stage="slot-lookup")
