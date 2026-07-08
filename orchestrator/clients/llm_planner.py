"""LLM plan provider — the ERP-driven, LLM-generated disassembly plan.

Reads the same per-product ERP dataset as StaticPlanProvider, but asks an LLM
(via OpenRouter) to produce the ordered steps with human instructions.

Guardrail: the LLM can only ORDER and DESCRIBE — every step's `part` must be a
part listed in the ERP entry, and every ERP part must appear exactly once. Any
violation (or any API error) falls back to the static ERP order, so plan
generation can never invent a part or block a run.
"""

from __future__ import annotations

import json

from ..config import OrchestratorConfig
from ..models import Plan, PlanStep
from .erp import build_static_plan, load_products

_SYSTEM = """You are a disassembly planner for a robot arm work cell.
Given a product's parts list from an ERP system, produce the ordered disassembly
plan. Respond with JSON only:
{"steps": [{"part": "<part id from the list>", "action": "<one-sentence instruction>"}],
 "rationale": "<one sentence on the ordering>"}
Rules: use each listed part EXACTLY once; do not invent parts; order steps so
each part is physically accessible when its turn comes (parts on top / blocking
others come first); instructions describe the removal motion, not tooling."""


class LlmPlanProvider:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    # seam for tests — monkeypatch this to stub the network call
    def _chat(self, messages: list[dict]) -> dict:
        from .openrouter import chat_json

        return chat_json(self.config, messages)

    def get_plan(self, product_id: str) -> Plan:
        products = load_products(self.config.erp_products_path)
        entry = products.get(product_id)
        if entry is None:
            known = ", ".join(sorted(products)) or "<none>"
            raise ValueError(f"unknown product {product_id!r} (known: {known})")

        try:
            raw = self._chat(self._messages(product_id, entry))
            return self._validated_plan(product_id, entry, raw)
        except ValueError:
            raise  # unknown product — not the LLM's fault, don't mask it
        except Exception as exc:
            # Any LLM/API/shape failure -> the ERP's own order still works.
            return build_static_plan(
                product_id, entry, source="static-fallback",
                rationale=f"LLM plan generation failed ({exc}); using ERP order",
            )

    def _messages(self, product_id: str, entry: dict) -> list[dict]:
        erp_view = {
            "product": product_id,
            "name": entry.get("name"),
            "description": entry.get("description"),
            "parts": [
                {"part": p["part"], "notes": p.get("notes")} for p in entry.get("parts", [])
            ],
        }
        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(erp_view)},
        ]

    def _validated_plan(self, product_id: str, entry: dict, raw: dict) -> Plan:
        known = [p["part"] for p in entry.get("parts", [])]
        steps_raw = raw.get("steps")
        if not isinstance(steps_raw, list) or not steps_raw:
            raise RuntimeError("LLM plan has no steps")
        parts = [s.get("part") for s in steps_raw]
        if sorted(parts) != sorted(known):
            raise RuntimeError(
                f"LLM plan parts {parts} != ERP parts {known} (must be a permutation)"
            )
        notes = {p["part"]: p.get("notes") for p in entry.get("parts", [])}
        steps = [
            PlanStep(
                part=s["part"],
                action=(s.get("action") or f"remove the {s['part']}").strip(),
                index=i + 1,
                notes=notes.get(s["part"]),
            )
            for i, s in enumerate(steps_raw)
        ]
        return Plan(product=product_id, steps=steps, source="llm",
                    rationale=raw.get("rationale"))
