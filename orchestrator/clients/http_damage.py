"""Damage-inspection stage client — talks to the damage service (/inspect)."""

from __future__ import annotations

import httpx

from ..config import OrchestratorConfig
from ..models import Inspection, PartDetection


class HttpDamage:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.c = config
        self._http = httpx.Client(timeout=config.http_timeout_s)

    def inspect(self, images_b64: list[str], part: PartDetection) -> Inspection:
        r = self._http.post(
            f"{self.c.damage_url}/inspect",
            json={"images_b64": images_b64, "part_class": part.class_name},
        )
        r.raise_for_status()
        d = r.json()
        return Inspection(
            verdict=d["verdict"],
            damaged=d["damaged"],
            bin=d["bin"],
            confidence=d.get("confidence", 0.0),
            issues=d.get("issues", []),
        )
