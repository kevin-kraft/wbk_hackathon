"""pose/shared/schemas.py — the `class` field aliasing (populate_by_name)."""

from __future__ import annotations

from shared.schemas import ObjectPose, PoseInstance, PoseRequest


def test_pose_instance_populates_by_alias_class():
    inst = PoseInstance(id=1, **{"class": "housing"}, mask_b64="abc")
    assert inst.cls == "housing"


def test_pose_instance_populates_by_field_name_cls():
    inst = PoseInstance(id=1, cls="housing", mask_b64="abc")
    assert inst.cls == "housing"


def test_pose_instance_serializes_by_alias():
    inst = PoseInstance(id=1, cls="housing", mask_b64="abc")
    dumped = inst.model_dump(by_alias=True)

    assert dumped["class"] == "housing"
    assert "cls" not in dumped


def test_object_pose_round_trips_class_alias_both_ways():
    pose_by_alias = ObjectPose(id=1, **{"class": "bracket"}, T_cam_obj=[[1, 0, 0, 0]] * 4)
    pose_by_name = ObjectPose(id=1, cls="bracket", T_cam_obj=[[1, 0, 0, 0]] * 4)

    assert pose_by_alias.cls == "bracket"
    assert pose_by_name.cls == "bracket"

    dumped = pose_by_alias.model_dump(by_alias=True)
    assert dumped["class"] == "bracket"
    assert "cls" not in dumped


def test_object_pose_json_dump_by_alias_emits_class():
    # FastAPI serializes response_model output with by_alias=True by default,
    # so this is what actually goes out over the wire (see pose/*/app.py).
    pose = ObjectPose(id="p1", cls="bracket", T_cam_obj=[[1, 0, 0, 0]] * 4)
    dumped_json = pose.model_dump_json(by_alias=True)

    assert '"class":"bracket"' in dumped_json.replace(" ", "")
    assert '"cls"' not in dumped_json


def test_pose_request_defaults():
    req = PoseRequest(
        rgb_b64="abc",
        K=[1, 0, 0, 0, 1, 0, 0, 0, 1],
        instances=[PoseInstance(id=0, cls="housing", mask_b64="m")],
    )

    assert req.depth_b64 is None
    assert req.iterations == 5
    assert req.hypotheses == 5
    assert req.pipeline == "rgbd"
    assert req.kabsch is True
