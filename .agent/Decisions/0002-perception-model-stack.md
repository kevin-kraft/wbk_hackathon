# ADR 0002: Perception model stack — YOLO + SAM 3 + LocateAnything

## Related Docs
- [Architecture](../System/architecture.md) — perception stage detail
- [Integration Points](../System/integration_points.md) — the `/infer` contract these three models share

## Status
Accepted (as scaffolded, 2026-07-07 — commit `82a88f9`).

## Context

Perception needs to do two things for the "identify the next part" and
"rectify grabbing mistakes" product jobs: detect/segment candidate parts, and
resolve a natural-language instruction ("the bracket next to the housing") to
a specific box/point/mask in the scene.

Per team discussion during scoping (not captured in git history — this repo's
commits start from the scaffold, `82a88f9`), an earlier idea for the
grounding/localization piece considered a general vision-language model such
as **Qwen2.5-VL** or **Molmo** doing pointing directly. That direction was
superseded before any code was committed — there is no trace of it in this
repository (checked: no reference to either name anywhere in the tracked
tree). This ADR exists to record *why* the team landed on the current stack
instead, for anyone who later wonders why a general VLM isn't in the
perception loop.

## Decision

Three purpose-built models, each its own FastAPI service:

- **YOLO** (Ultralytics) — fast, well-understood object detection to propose
  candidate parts.
- **SAM 3** (`facebook/sam3`) — promptable segmentation with both classic
  point/box prompts (tracker head) and SAM3's headline **text/concept**
  prompting (concept head) — segments *all* instances matching a
  noun-phrase in one call.
- **LocateAnything-3B** (NVIDIA) — a dedicated grounding/pointing model:
  text query in, boxes/points out, via its own special-token output format.

## Why

- **Task-specialized models over a general VLM for grounding.** LocateAnything
  is purpose-built for text→box/point grounding and returns structured,
  parseable output (`<box><a><b><c><d></box>` tokens) rather than requiring
  the caller to prompt-engineer a general VLM into emitting coordinates
  reliably. SAM3's concept head gives multi-instance segmentation for free
  from a single text prompt, which a general VLM would not provide without an
  additional segmentation pass.
- **Composability with existing geometry primitives.** All three models'
  outputs converge on the same `BBox`/`Point` shared types
  (`perception/services/shared/schemas.py`), so downstream stages (pose,
  future grasp planning) don't need to special-case which model produced a
  given detection. A general VLM's free-text or inconsistent-format output
  would need an extra normalization layer to fit this contract.
- **SAM 3 is current (released 2025-11)** and already has first-class
  `transformers` integration (`Sam3Model`/`Sam3Processor`,
  `Sam3TrackerModel`/`Sam3TrackerProcessor`), avoiding a bespoke integration
  layer.

## Consequences

- LocateAnything has **no native per-instance confidence score** — its output
  is a ranked list (Parallel Box Decoding order), so
  `LocateAnythingBackend._parse()` derives a rank-based pseudo-score
  (`1.0 - i/n`) to satisfy the shared response contract. Callers should treat
  this score as an ordering hint, not a calibrated probability.
- LocateAnything loads via `trust_remote_code=True` (custom
  `py_apply_chat_template`/`process_vision_info`/`generation_mode` methods) —
  the model's remote code can change upstream independent of this repo; the
  README flags pinning a revision in production.
- SAM 3 weights (`facebook/sam3`) are **gated** on HuggingFace — first run
  requires `hf auth login` (or `HF_TOKEN`) with access already granted. See
  [SOP: running the services](../SOP/running_services.md).
- If a future need arises for open-ended visual reasoning beyond
  detection/segmentation/grounding (e.g. "does this look assembled
  correctly?"), that is a separate concern already handled by a general VLM
  elsewhere in the pipeline — the damage-inspection stage uses OpenRouter
  (default `anthropic/claude-sonnet-5`) for exactly that kind of judgment call
  (see [ADR 0003](./0003-damage-failsafe-sort-policy.md)). Perception was
  deliberately kept to specialized, structured-output models.
