"""Slot-localization: layout schema, top-down pose math, and the occupancy engine.

Covers the depth-free path that replaces the pose stage when
localization_mode="slots" (orchestrator/slots.py + clients/slot_perception.py).
"""

from __future__ import annotations

import numpy as np

from orchestrator.config import OrchestratorConfig
from orchestrator.models import SceneFrame
from orchestrator.slots import (
    SlotLayout,
    SlotSpec,
    compute_occupancy,
    decode_mask,
    layout_from_dict,
    pose4x4_from_xyz_yaw,
)


def _disk_mask(h, w, cx, cy, r):
    yy, xx = np.mgrid[0:h, 0:w]
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r


def _layout(**kw):
    slots = [
        SlotSpec(id="A1", expected_class="anker_kurz", pixel=(100, 100), base_xyz_m=(0.3, -0.1, 0.02)),
        SlotSpec(id="A2", expected_class="poltopf_kurz", pixel=(300, 100), base_xyz_m=(0.3, 0.1, 0.02)),
    ]
    return SlotLayout(slots=slots, image_size=(400, 200), radius_px=20, fill_frac=0.35, **kw)


# --- pose math ------------------------------------------------------------- #

def test_pose_is_top_down_with_translation():
    T = pose4x4_from_xyz_yaw([0.3, -0.1, 0.02], yaw_deg=0.0)
    assert T[0][3] == 0.3 and T[1][3] == -0.1 and T[2][3] == 0.02
    # Tool z-axis (3rd column of R) points straight down in the base frame.
    assert [T[0][2], T[1][2], T[2][2]] == [0.0, 0.0, -1.0]
    assert T[3] == [0.0, 0.0, 0.0, 1.0]


def test_pose_yaw_rotates_about_base_z():
    T = pose4x4_from_xyz_yaw([0, 0, 0], yaw_deg=90.0)
    # cos90≈0, sin90≈1 -> tool x-axis = (c, s, 0) ≈ (0, 1, 0).
    assert abs(T[0][0]) < 1e-9 and abs(T[1][0] - 1.0) < 1e-9


# --- layout roundtrip ------------------------------------------------------ #

def test_layout_dict_roundtrip():
    layout = _layout(mask_source="yoloseg", name="tray")
    again = layout_from_dict(layout.to_dict())
    assert again.name == "tray"
    assert again.mask_source == "yoloseg"
    assert [s.id for s in again.slots] == ["A1", "A2"]
    assert again.slots[0].base_xyz_m == (0.3, -0.1, 0.02)
    assert again.classes == ["anker_kurz", "poltopf_kurz"]


# --- occupancy ------------------------------------------------------------- #

def test_occupancy_flags_filled_slot_and_identity():
    layout = _layout()
    # A mask of anker_kurz sitting on A1's centre (100,100); nothing on A2.
    masks = [("anker_kurz", _disk_mask(200, 400, 100, 100, 25))]
    statuses = compute_occupancy(masks, layout)
    by_id = {s.slot_id: s for s in statuses}
    assert by_id["A1"].filled and by_id["A1"].detected_class == "anker_kurz"
    assert by_id["A1"].identity_ok
    assert by_id["A1"].base_pose[0][3] == 0.3  # slot's measured coordinate
    assert not by_id["A2"].filled and by_id["A2"].detected_class is None


def test_occupancy_identity_mismatch_when_wrong_part():
    layout = _layout()
    # A poltopf mask covers A1, whose expected class is anker_kurz.
    masks = [("poltopf_kurz", _disk_mask(200, 400, 100, 100, 25))]
    a1 = next(s for s in compute_occupancy(masks, layout) if s.slot_id == "A1")
    assert a1.filled and a1.detected_class == "poltopf_kurz"
    assert not a1.identity_ok


def test_occupancy_scales_pixels_to_actual_resolution():
    layout = _layout()  # calibrated at 400x200
    # Capture at 2x (800x400): the slot at (100,100) now maps to (200,200).
    masks = [("anker_kurz", _disk_mask(400, 800, 200, 200, 45))]
    a1 = next(s for s in compute_occupancy(masks, layout) if s.slot_id == "A1")
    assert a1.filled
    assert abs(a1.pixel[0] - 200) < 1 and abs(a1.pixel[1] - 200) < 1


def test_decode_mask_roundtrips_png():
    import base64
    import io

    from PIL import Image

    arr = (_disk_mask(64, 64, 32, 32, 10) * 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    decoded = decode_mask(b64)
    assert decoded.dtype == bool and decoded[32, 32] and not decoded[0, 0]


# --- slot-mode wiring ------------------------------------------------------ #

def test_slot_perception_returns_filled_slot_with_pose():
    from orchestrator.clients.slot_perception import SlotPerception

    layout = _layout()

    class FakePerception:
        def segment_all(self, frame, text):
            import io

            import numpy as np
            from PIL import Image

            if text != "anker_kurz":
                return []
            arr = (_disk_mask(200, 400, 100, 100, 25) * 255).astype("uint8")
            buf = io.BytesIO()
            Image.fromarray(arr, mode="L").save(buf, format="PNG")
            import base64

            return [base64.b64encode(buf.getvalue()).decode()]

    sp = SlotPerception(OrchestratorConfig(), FakePerception(), layout=layout)
    part = sp.next_part(SceneFrame(rgb_b64="x"))
    assert part is not None
    assert part.class_name == "anker_kurz" and part.id == "A1"
    assert part.slot_pose is not None and part.slot_pose[0][3] == 0.3


def _b64_disk(h, w, cx, cy, r):
    import base64
    import io

    from PIL import Image

    arr = (_disk_mask(h, w, cx, cy, r) * 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_full_loop_disassembles_by_slot_occupancy():
    """End-to-end: the real DisassemblyOrchestrator in slot mode removes every
    filled slot and stops when the tray reads empty — SlotPerception + SlotPose +
    SlotGraspPlanner driving the unchanged state machine."""
    from orchestrator import mocks
    from orchestrator.clients.slot_grasp import SlotGraspPlanner
    from orchestrator.clients.slot_perception import SlotPerception, SlotPose
    from orchestrator.loop import DisassemblyOrchestrator

    layout = _layout()  # A1 anker@ (100,100), A2 poltopf@ (300,100), 400x200

    class World:
        """Models which slots still hold a part; masks reflect the current state."""

        def __init__(self):
            self.present = {"A1": True, "A2": True}
            self.by_pixel = {"A1": (100, 100), "A2": (300, 100)}
            self.by_class = {"anker_kurz": ["A1"], "poltopf_kurz": ["A2"]}
            self.current = None

        def segment_all(self, frame, text):
            out = []
            for sid in self.by_class.get(text, []):
                if self.present[sid]:
                    cx, cy = self.by_pixel[sid]
                    out.append(_b64_disk(200, 400, cx, cy, 25))
            return out

        def segment(self, frame, part):  # records the grasp target for the lift
            self.current = part.id
            return _b64_disk(200, 400, *self.by_pixel[part.id], 25)

        def remove_current(self):
            if self.current:
                self.present[self.current] = False
                self.current = None

    world = World()

    class LiftingMovement(mocks.MockMovement):
        def move_named(self, name: str) -> None:
            super().move_named(name)
            if name == "clearance":  # the part has been lifted clear -> slot empties
                world.remove_current()

    orch = DisassemblyOrchestrator(
        scene_camera=mocks.MockSceneCamera(),
        perception=SlotPerception(OrchestratorConfig(), world, layout=layout),
        pose=SlotPose(),
        grasp=SlotGraspPlanner(OrchestratorConfig()),
        movement=LiftingMovement(),
        grip=mocks.MockGrip(fail_first=False),
        inspection_camera=mocks.MockInspectionCamera(),
        damage=mocks.MockDamage(damaged_classes=set()),
        config=OrchestratorConfig(inspection_angles=1),
    )
    stats = orch.run()
    assert stats["removed"] == 2
    assert stats["ok_bin"] == 2
    assert stats["skipped"] == 0
    assert any(e.state == "DONE" for e in orch.events)
    # The grasp used the slot's measured base coordinate, not a back-projection.
    assert any(e.state == "POSE" and e.data.get("stage") == "slot-lookup" for e in orch.events)


def test_slot_grasp_uses_slot_pose():
    from orchestrator.clients.slot_grasp import SlotGraspPlanner
    from orchestrator.models import PartDetection, Pose

    planner = SlotGraspPlanner(OrchestratorConfig())
    pose = pose4x4_from_xyz_yaw([0.3, -0.1, 0.02], 0.0)
    part = PartDetection(class_name="anker_kurz", id="A1", slot_pose=pose)
    grasp = planner.plan(Pose(T_cam_obj=[[1]]), part)
    assert grasp.T_base_grasp[0][3] == 0.3
    assert grasp.meta["slot_id"] == "A1"
    # Pre-grasp stands off ABOVE the slot (tool z points down -> -z is up).
    assert grasp.pre_grasp[2][3] > grasp.T_base_grasp[2][3]
