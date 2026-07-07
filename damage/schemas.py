"""Wire contract for the damage-inspection stage."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DamageRequest(BaseModel):
    """Images of ONE disassembled part, captured from several angles by the
    inspection webcam, to be judged OK vs damaged.

    Reference examples (known-good / known-damaged of the same part type) can be
    passed inline here and/or loaded from disk by `part_class` (see REFERENCE_DIR).
    """

    images_b64: list[str] = Field(..., min_length=1, description="Target part, multiple angles.")
    part_class: str | None = Field(None, description="Part type, for disk-backed references + prompt.")
    reference_ok_b64: list[str] = Field(default_factory=list)
    reference_damaged_b64: list[str] = Field(default_factory=list)
    notes: str | None = Field(None, description="Extra inspection guidance for this part.")


class DamageVerdict(BaseModel):
    verdict: Literal["ok", "damaged", "uncertain"]
    damaged: bool
    confidence: float  # 0..1, model's self-reported confidence
    bin: Literal["ok_bin", "reject_bin"]  # where the arm should place the part
    issues: list[str] = Field(default_factory=list)  # observed defects
    reasoning: str
    model: str
    part_class: str | None = None


class DamageHealth(BaseModel):
    status: str
    service: str
    model: str
    api_key_present: bool
    reference_dir: str
