"""Mock-ERP plan provider — the static half of the head-of-pipeline seam.

"ERP data" for the hackathon is a per-product JSON dataset (ERP_PRODUCTS_PATH,
default: the packaged orchestrator/data/erp_products.json). `StaticPlanProvider`
turns a product entry into a Plan in the listed order — no LLM involved. A real
ERP client would implement the same `PlanProvider` Protocol and drop in with no
loop changes (the same play as ADR 0005's mock-first seams).

Standard library only, so the dry-run/tests never need extra deps.
"""

from __future__ import annotations

import json
import os

from ..config import OrchestratorConfig
from ..models import Plan, PlanStep


def load_products(path: str) -> dict:
    """The raw products map: {product_id: {name, description, parts: [...]}}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    products = data.get("products")
    if not isinstance(products, dict):
        raise ValueError(f"{path}: expected a top-level 'products' object")
    return products


def build_static_plan(product_id: str, entry: dict, *, source: str = "static",
                      rationale: str | None = None) -> Plan:
    """A plan straight from the ERP entry, steps in the listed (ERP) order."""
    steps = [
        PlanStep(
            part=p["part"],
            action=p.get("action") or f"remove the {p['part']}",
            index=i + 1,
            notes=p.get("notes"),
        )
        for i, p in enumerate(entry.get("parts", []))
    ]
    if not steps:
        raise ValueError(f"product {product_id!r} has no parts")
    return Plan(product=product_id, steps=steps, source=source, rationale=rationale)


class StaticPlanProvider:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.path = config.erp_products_path

    def get_plan(self, product_id: str) -> Plan:
        products = load_products(self.path)
        entry = products.get(product_id)
        if entry is None:
            known = ", ".join(sorted(products)) or "<none>"
            raise ValueError(f"unknown product {product_id!r} (known: {known})")
        return build_static_plan(product_id, entry)


def default_products_path() -> str:
    """The dataset packaged with the orchestrator image."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "erp_products.json")
