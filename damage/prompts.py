"""Prompt construction for the damage-inspection VLM call."""

from __future__ import annotations

from .schemas import DamageRequest

SYSTEM_PROMPT = (
    "You are a meticulous industrial quality-control inspector examining a "
    "mechanical part that a robot arm has just disassembled and is holding up to "
    "an inspection camera. You are shown reference images of KNOWN-GOOD (OK) and "
    "KNOWN-DAMAGED examples of the same part type, then several images of the "
    "TARGET part from different angles.\n\n"
    "Decide whether the target part is OK or DAMAGED. Damage includes: cracks, "
    "chips, fractures, bends/deformation, dents, corrosion/rust, missing material, "
    "stripped or damaged threads, burns, melting, and discoloration indicating "
    "overheating or wear. Ignore harmless dust, reflections, lighting, and "
    "background. Judge the part across ALL angles together — a defect visible in "
    "any single view means the part is damaged.\n\n"
    "Be conservative for a sorting task: if clear damage is present, mark it "
    "'damaged'. If genuinely ambiguous, use 'uncertain'."
)

RESPONSE_INSTRUCTION = (
    "Respond with ONLY a JSON object, no prose, of exactly this shape:\n"
    '{\n'
    '  "verdict": "ok" | "damaged" | "uncertain",\n'
    '  "confidence": <float 0..1>,\n'
    '  "issues": [<short strings naming each observed defect, empty if none>],\n'
    '  "reasoning": "<one or two sentences>"\n'
    '}'
)


def _image_part(b64: str) -> dict:
    url = b64 if b64.strip().startswith("data:") else f"data:image/png;base64,{b64}"
    return {"type": "image_url", "image_url": {"url": url}}


def build_messages(
    req: DamageRequest,
    ref_ok: list[str],
    ref_damaged: list[str],
) -> list[dict]:
    content: list[dict] = []

    if ref_ok:
        content.append({"type": "text", "text": "Reference images of KNOWN-GOOD (OK) parts:"})
        content.extend(_image_part(b) for b in ref_ok)
    if ref_damaged:
        content.append({"type": "text", "text": "Reference images of KNOWN-DAMAGED parts:"})
        content.extend(_image_part(b) for b in ref_damaged)

    header = "Target part"
    if req.part_class:
        header += f" (type: {req.part_class})"
    header += " — images from different angles. Assess OK vs damaged:"
    content.append({"type": "text", "text": header})
    content.extend(_image_part(b) for b in req.images_b64)

    if req.notes:
        content.append({"type": "text", "text": f"Additional guidance: {req.notes}"})
    content.append({"type": "text", "text": RESPONSE_INSTRUCTION})

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
