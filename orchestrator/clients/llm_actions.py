"""LLM action synthesizer — picks arm actions from the constrained vocabulary.

The runtime command-synthesis piece of the vision: instruction (plan step) +
part + grasp context in, action sequence out. The LLM never sees or emits
coordinates — it can only reference pipeline-computed poses by name
(actions.VOCABULARY_DOC is its entire command surface), and the loop validates
whatever comes back with `validate_actions`, falling back to the scripted
sequence on any violation. See ADR 0011.
"""

from __future__ import annotations

import json

from ..actions import VOCABULARY_DOC
from ..config import OrchestratorConfig
from ..models import Grasp, PartDetection, PlanStep

_SYSTEM = f"""You select motion primitives for a robot arm that is about to grasp
a part during disassembly. {VOCABULARY_DOC}
Respond with JSON only: {{"actions": [ ... ]}}"""


class LlmActionSynthesizer:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    # seam for tests — monkeypatch this to stub the network call
    def _chat(self, messages: list[dict]) -> dict:
        from .openrouter import chat_json

        return chat_json(self.config, messages)

    def synthesize(self, part: PartDetection, grasp: Grasp, step: PlanStep | None) -> list:
        context = {
            "part": part.class_name,
            "instruction": step.action if step else f"grasp the {part.class_name}",
            "notes": step.notes if step else None,
            "pre_grasp_available": grasp.pre_grasp is not None,
        }
        raw = self._chat([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(context)},
        ])
        actions = raw.get("actions")
        if not isinstance(actions, list):
            raise RuntimeError("LLM returned no 'actions' list")
        return actions  # validated by the loop's validate_actions guardrail
