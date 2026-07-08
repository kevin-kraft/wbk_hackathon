"""Plan-driven loop, plan providers, and the constrained action vocabulary.

Covers the LLM-orchestration extension (see .agent/Tasks/active/
llm_orchestrated_disassembly_plan.md): plan generation seams (static ERP /
LLM-with-fallback), the plan-driven outer loop, and the validate->execute
guardrail that keeps LLM-proposed motion inside the fixed vocabulary.
Mocks only — no network, no LLM, no hardware.
"""

from __future__ import annotations

import json

import pytest

from orchestrator import mocks
from orchestrator.actions import (
    ActionValidationError,
    execute_actions,
    scripted_grasp_sequence,
    validate_actions,
)
from orchestrator.config import OrchestratorConfig
from orchestrator.loop import DisassemblyOrchestrator
from orchestrator.models import ArmAction, Grasp


def _identity4x4():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def _build(grip=None, parts=None, plan_provider=None, synthesizer=None):
    return DisassemblyOrchestrator(
        scene_camera=mocks.MockSceneCamera(),
        perception=mocks.MockPerception(parts or ["cover", "bracket", "gear"]),
        pose=mocks.MockPose(),
        grasp=mocks.MockGraspPlanner(),
        movement=mocks.MockMovement(),
        grip=grip or mocks.MockGrip(fail_first=False),
        inspection_camera=mocks.MockInspectionCamera(),
        damage=mocks.MockDamage({"gear"}),
        plan_provider=plan_provider or mocks.MockPlanProvider(),
        synthesizer=synthesizer,
        config=OrchestratorConfig(inspection_angles=2),
    )


# --------------------------------------------------------------------- #
# plan-driven loop
# --------------------------------------------------------------------- #

def test_plan_driven_run_completes_and_sorts():
    orch = _build()
    stats = orch.run(product="gearbox-demo")
    assert stats == {"removed": 3, "ok_bin": 2, "reject_bin": 1, "skipped": 0}
    states = [e.state for e in orch.events]
    assert states[0] == "PLAN_GENERATED"
    assert states.count("STEP") == 3
    assert "DONE" in states


def test_plan_event_carries_the_full_plan():
    orch = _build()
    orch.run(product="gearbox-demo")
    plan_event = orch.events[0]
    assert plan_event.data["product"] == "gearbox-demo"
    assert [s["part"] for s in plan_event.data["steps"]] == ["cover", "bracket", "gear"]


def test_plan_order_is_followed():
    provider = mocks.MockPlanProvider(steps=[
        ("gear", "pull the gear"), ("cover", "lift the cover"), ("bracket", "slide the bracket"),
    ])
    orch = _build(plan_provider=provider)
    orch.run(product="x")
    located = [e.data["part"] for e in orch.events if e.state == "LOCATE"]
    assert located == ["gear", "cover", "bracket"]


def test_uncompletable_plan_step_blocks_the_run():
    # Grip never confirms -> first step can't complete -> ordered plan is blocked.
    orch = _build(grip=mocks.MockGrip(always_fail=True))
    stats = orch.run(product="gearbox-demo")
    assert stats["removed"] == 0
    states = [e.state for e in orch.events]
    assert "BLOCKED" in states
    assert states.count("STEP") == 1  # later steps never attempted


def test_part_missing_from_scene_skips_the_step():
    provider = mocks.MockPlanProvider(steps=[
        ("widget", "remove the widget"),  # never in the mock scene
        ("cover", "lift the cover"),
    ])
    orch = _build(parts=["cover"], plan_provider=provider)
    stats = orch.run(product="x")
    assert stats["removed"] == 1
    assert stats["skipped"] == 1
    assert any(e.state == "SKIP" and e.data.get("part") == "widget" for e in orch.events)
    assert any(e.state == "DONE" for e in orch.events)


def test_plan_run_without_provider_raises():
    orch = _build()
    orch.plan_provider = None
    with pytest.raises(ValueError, match="no PlanProvider"):
        orch.run(product="gearbox-demo")


def test_fixed_mode_unaffected_by_plan_wiring():
    orch = _build()
    stats = orch.run()  # no product -> perception-driven, as before
    assert stats["removed"] == 3
    assert not any(e.state in ("PLAN_GENERATED", "STEP") for e in orch.events)


# --------------------------------------------------------------------- #
# action synthesis + guardrail
# --------------------------------------------------------------------- #

def test_synthesized_actions_drive_the_grasp():
    synth = mocks.MockActionSynthesizer()
    orch = _build(synthesizer=synth)
    stats = orch.run(product="gearbox-demo")
    assert stats["removed"] == 3
    assert synth.calls == 3
    assert not any(e.state == "GUARDRAIL" for e in orch.events)


def test_bad_synthesizer_output_falls_back_to_scripted():
    synth = mocks.MockActionSynthesizer(bad=True)  # emits raw coordinates -> rejected
    orch = _build(synthesizer=synth)
    stats = orch.run(product="gearbox-demo")
    assert stats["removed"] == 3  # scripted fallback still grasps everything
    assert any(e.state == "GUARDRAIL" for e in orch.events)


def test_crashing_synthesizer_falls_back_to_scripted():
    class Crashing:
        def synthesize(self, part, grasp, step):
            raise RuntimeError("LLM down")

    orch = _build(synthesizer=Crashing())
    stats = orch.run(product="gearbox-demo")
    assert stats["removed"] == 3
    assert any(e.state == "GUARDRAIL" for e in orch.events)


# --------------------------------------------------------------------- #
# the vocabulary validator (the safety boundary)
# --------------------------------------------------------------------- #

def test_validator_accepts_canonical_grasp_sequence():
    actions = validate_actions([
        {"kind": "move_to_pose", "pose_ref": "pre_grasp"},
        {"kind": "move_to_pose", "pose_ref": "grasp"},
        {"kind": "gripper", "closed": True},
    ])
    assert [a.kind for a in actions] == ["move_to_pose", "move_to_pose", "gripper"]


@pytest.mark.parametrize("bad", [
    [],  # empty
    [{"kind": "self_destruct"}],  # unknown kind
    [{"kind": "move_to_pose", "pose": [[1, 0, 0, 0]]}],  # raw coordinates
    [{"kind": "move_to_pose", "pose_ref": "somewhere"}],  # unknown pose ref
    [{"kind": "move_named", "name": "ok_bin"}, {"kind": "gripper", "closed": True}],  # bin move not allowed mid-grasp
    [{"kind": "move_named", "name": "warp_speed"}, {"kind": "gripper", "closed": True}],  # unknown named pose
    [{"kind": "move_to_pose", "pose_ref": "grasp"}],  # no gripper close at the end
    [{"kind": "gripper", "closed": True}, {"kind": "move_to_pose", "pose_ref": "grasp"}],  # close not last
    [{"kind": "gripper", "closed": True, "width": 5.0}],  # width out of range
    [{"kind": "gripper", "closed": True}] * 20,  # too many actions
])
def test_validator_rejects_out_of_vocabulary(bad):
    with pytest.raises(ActionValidationError):
        validate_actions(bad)


def test_executor_resolves_pose_refs_from_the_grasp():
    movement = mocks.MockMovement()
    grasp = Grasp(T_base_grasp=_identity4x4(), pre_grasp=None, width=0.03)
    actions = validate_actions([
        {"kind": "move_to_pose", "pose_ref": "pre_grasp"},  # None -> skipped
        {"kind": "move_to_pose", "pose_ref": "grasp"},
        {"kind": "gripper", "closed": True},
    ])
    execute_actions(actions, movement, grasp)
    assert movement.calls == [("move_to_pose",), ("set_gripper", True)]


def test_scripted_sequence_matches_original_loop_motion():
    grasp = Grasp(T_base_grasp=_identity4x4(), pre_grasp=_identity4x4(), width=0.04)
    seq = scripted_grasp_sequence(grasp)
    assert [(a.kind, a.pose_ref or a.closed) for a in seq] == [
        ("move_to_pose", "pre_grasp"), ("move_to_pose", "grasp"), ("gripper", True),
    ]
    assert isinstance(seq[0], ArmAction)


# --------------------------------------------------------------------- #
# plan providers
# --------------------------------------------------------------------- #

_ERP = {
    "products": {
        "widget-1": {
            "name": "Widget",
            "description": "test product",
            "parts": [
                {"part": "lid", "action": "lift the lid", "notes": "loose"},
                {"part": "core", "action": "pull the core"},
            ],
        }
    }
}


@pytest.fixture()
def erp_config(tmp_path):
    path = tmp_path / "erp.json"
    path.write_text(json.dumps(_ERP))
    return OrchestratorConfig(erp_products_path=str(path))


def test_static_provider_follows_erp_order(erp_config):
    from orchestrator.clients.erp import StaticPlanProvider

    plan = StaticPlanProvider(erp_config).get_plan("widget-1")
    assert plan.source == "static"
    assert [(s.part, s.index) for s in plan.steps] == [("lid", 1), ("core", 2)]
    assert plan.steps[0].notes == "loose"


def test_static_provider_unknown_product_raises(erp_config):
    from orchestrator.clients.erp import StaticPlanProvider

    with pytest.raises(ValueError, match="unknown product"):
        StaticPlanProvider(erp_config).get_plan("nope")


def test_llm_provider_uses_validated_llm_order(erp_config, monkeypatch):
    from orchestrator.clients.llm_planner import LlmPlanProvider

    provider = LlmPlanProvider(erp_config)
    monkeypatch.setattr(provider, "_chat", lambda messages: {
        "steps": [{"part": "core", "action": "pull the core first"},
                  {"part": "lid", "action": "then lift the lid"}],
        "rationale": "core blocks nothing",
    })
    plan = provider.get_plan("widget-1")
    assert plan.source == "llm"
    assert [s.part for s in plan.steps] == ["core", "lid"]
    assert plan.steps[0].index == 1


def test_llm_provider_rejects_invented_parts_and_falls_back(erp_config, monkeypatch):
    from orchestrator.clients.llm_planner import LlmPlanProvider

    provider = LlmPlanProvider(erp_config)
    monkeypatch.setattr(provider, "_chat", lambda messages: {
        "steps": [{"part": "warp_core", "action": "eject it"}],
    })
    plan = provider.get_plan("widget-1")
    assert plan.source == "static-fallback"  # ERP order, not the invented part
    assert [s.part for s in plan.steps] == ["lid", "core"]


def test_llm_provider_falls_back_on_api_error(erp_config, monkeypatch):
    from orchestrator.clients.llm_planner import LlmPlanProvider

    provider = LlmPlanProvider(erp_config)

    def boom(messages):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(provider, "_chat", boom)
    plan = provider.get_plan("widget-1")
    assert plan.source == "static-fallback"
    assert "connection refused" in (plan.rationale or "")


def test_llm_provider_unknown_product_still_raises(erp_config, monkeypatch):
    from orchestrator.clients.llm_planner import LlmPlanProvider

    provider = LlmPlanProvider(erp_config)
    monkeypatch.setattr(provider, "_chat", lambda messages: {"steps": []})
    with pytest.raises(ValueError, match="unknown product"):
        provider.get_plan("nope")


# --------------------------------------------------------------------- #
# API surface
# --------------------------------------------------------------------- #

def test_products_and_plan_endpoints(monkeypatch):
    from fastapi.testclient import TestClient

    from orchestrator.app import app

    # Force the static provider even if the dev shell exports an OpenRouter key.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(app)
    r = client.get("/products")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["products"]]
    assert "gearbox-demo" in ids

    r = client.get("/plan", params={"product": "gearbox-demo", "dry_run": True})
    assert r.status_code == 200
    assert [s["part"] for s in r.json()["steps"]] == ["cover", "bracket", "gear"]

    r = client.get("/plan", params={"product": "gearbox-demo"})  # static provider (no key)
    assert r.status_code == 200
    assert r.json()["source"] == "static"

    r = client.get("/plan", params={"product": "nope"})
    assert r.status_code == 404


def test_run_endpoint_accepts_product():
    from fastapi.testclient import TestClient

    from orchestrator.app import app

    client = TestClient(app)
    r = client.post("/run", params={"dry_run": True, "product": "gearbox-demo"})
    assert r.status_code == 200
    body = r.json()
    assert body["product"] == "gearbox-demo"
    assert body["stats"]["removed"] == 3
    assert body["events"][0]["state"] == "PLAN_GENERATED"
