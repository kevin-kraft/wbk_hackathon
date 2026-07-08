# ADR 0011 — The command-synthesis LLM is an action *selector*, not a command *generator*

## Related Docs
- [System: Orchestrator](../System/orchestrator.md) — plan mode, the `ActionSynthesizer` seam, `_grasp_actions`/`_grasp_with_retry`
- [ADR 0010: robot_control integration](./0010-robot-control-integration.md) — the still-open orchestrator↔movement adapter gap this vocabulary is designed to eventually map onto
- [ADR 0006: eye-to-hand static calibration](./0006-eye-to-hand-static-calibration.md) — where the pipeline-computed `pre_grasp`/`grasp` poses this ADR's vocabulary references actually come from
- [ADR 0005: mock-first, interface-seam integration](./0005-mock-first-interface-seam-integration.md) — the same seam-before-hardware posture this ADR follows (`ActionSynthesizer` is optional, `None` by default)
- `Tasks/archive/llm_orchestrated_disassembly_plan.md` — the PRD this ADR resolves open question 3 for
- `orchestrator/actions.py` — the implementation (`validate_actions`, `scripted_grasp_sequence`, `execute_actions`, `VOCABULARY_DOC`)
- `contracts/movement_api.md` — the wire shape (`move_to_pose`/`move_named`/`gripper`) the vocabulary's action kinds mirror

## Context

The PRD (`Tasks/active/llm_orchestrated_disassembly_plan.md`, now archived)
proposed an LLM that synthesizes arm commands per plan step from three
inputs: the step's instruction, the part's 6DoF pose, and the movement-API
docs. It flagged this as **safety-critical and explicitly unresolved**: any
mechanism that lets an LLM's output reach a real robot arm without a
deterministic gate is unacceptable, because a malformed or hallucinated
command doesn't fail loudly like a schema mismatch — it moves a physical arm
somewhere wrong. Three candidate guardrails were listed without a decision:
a fixed named-pose vocabulary, schema-validated structured output, or some
other mechanism layered on top of `robot_control/`'s existing workspace/
velocity gates.

## Decision

**The LLM never sees or emits coordinates.** It selects from a small, closed
action vocabulary (`orchestrator/actions.py`); every pose it can reference is
computed by the pipeline (pose stage → `NaiveTopDownGrasp` grasp chain, see
ADR 0006) beforehand, and the LLM can only point at it by name (`pose_ref:
"pre_grasp" | "grasp"`). This is stricter than "schema-validated structured
output" — a structured-output schema can still contain a free-form matrix
field; this vocabulary has no such field to fill in.

**Vocabulary** (`ACTION_KINDS`, `VOCABULARY_DOC` — the literal text rendered
into the synthesizer's system prompt, so the prompt and the validator can
never drift):
- `move_to_pose` — `pose_ref` ∈ `{pre_grasp, grasp}` only.
- `move_named` — in the grasp context, `name` ∈ `{home, clearance}` only
  (a strict subset of the full named-pose universe `{home, clearance,
  ok_bin, reject_bin, inspect_0..N}` that `contracts/movement_api.md`
  defines — bins and inspect poses aren't reachable actions mid-grasp).
- `gripper` — `closed: bool`, optional bounded `width` (`0 < width <=
  0.20` m).

**Deterministic validation, not best-effort parsing.** `validate_actions()`
rejects the WHOLE sequence on any violation: unknown kind, unknown/
out-of-context named pose, a `pose_ref` outside `{pre_grasp, grasp}`, any
stray field on the wrong action kind (e.g. `closed` on a `move_named`), more
than `MAX_ACTIONS` (8) steps, or — the semantic invariant for the grasp
context — a sequence that doesn't end with exactly one `gripper closed=true`
(that close is what the grip-sensor check right after is verifying; a
sequence that doesn't end there isn't a completed grasp attempt). Validation
runs **before** anything reaches a `MovementClient` — `execute_actions()` is
only ever called on an already-validated list.

**Scripted fallback, not a retry loop.** `loop.py`'s `_grasp_actions()`
catches `ActionValidationError` (and any other exception from synthesis
itself — a network error, a malformed LLM response) and falls back to
`scripted_grasp_sequence(grasp)`, which reproduces exactly the motion the
loop always performed (pre_grasp → grasp → gripper close). It emits a new
`GUARDRAIL` `LoopEvent` so the fallback is visible in the demo narration and
the dashboard, not silent. No retry-with-a-different-prompt: one rejection
means "use the deterministic path for this attempt," full stop.

**Opt-in, off by default.** `ACTION_SYNTHESIS=scripted` (the default) never
constructs a synthesizer at all (`factory.py`'s `_build_synthesizer` returns
`None`) — the motion path is byte-for-byte what it was before this feature
existed. `ACTION_SYNTHESIS=llm` wires `LlmActionSynthesizer`
(`orchestrator/clients/llm_actions.py`, via OpenRouter — see "reuse the
existing provider" below) and requires `OPENROUTER_API_KEY`.

**`robot_control/`'s server-side gates remain the independent second
layer.** This vocabulary constrains what an LLM can *propose*; it says
nothing about workspace bounds, velocity limits, or collision checks on the
resulting motion — those are `robot_control/`'s hover-planning safety gates
(see [System: Robot Control](../System/robot_control.md)), which apply
regardless of whether a command originated from the scripted sequence or an
LLM selection. Two independent layers: vocabulary-shape validation here,
physical-motion validation there.

## Alternatives considered

- **Free-form 4x4 TCP poses from the LLM, schema-validated.** Rejected
  outright — even a strict JSON-schema-valid 4x4 matrix could be numerically
  wrong (hallucinated translation, flipped rotation), and there is no
  deterministic way to validate "is this SE(3) matrix a sane grasp pose for
  this part" short of recomputing it from the pipeline anyway. If the
  pipeline has to compute the correct pose to validate it, the LLM
  computing it too is pure redundant risk with no offsetting benefit.
- **Schema-only validation without pose indirection** (i.e., let the LLM
  emit a `pose_ref`-shaped object but also allow a raw-matrix field as a
  fallback "for flexibility"). Rejected — any escape hatch big enough to
  carry a matrix is big enough to carry a wrong one; the vocabulary is only
  as safe as its narrowest option.
- **A softer failure mode** (e.g., clamp an out-of-range value instead of
  rejecting the whole sequence). Rejected — clamping implies the system
  knows what the "safe" value should have been, which defeats the point of
  having an explicit vocabulary; reject-and-fall-back is simpler to reason
  about and impossible to under-guard by mistake.

## Consequences

- The LLM's contribution is real but bounded: it can choose *whether* to do
  a pre-grasp stand-off, *when* to close the gripper relative to named
  moves, and (via `LlmActionSynthesizer`'s prompt context — instruction +
  notes) let the plan step's language influence that choice. It cannot
  influence *where* the arm goes beyond the two pipeline-computed poses.
- `VOCABULARY_DOC` is both documentation and the prompt text — if the
  vocabulary changes (e.g. a new `pose_ref` is added), the prompt and the
  validator update together by construction, but anyone editing
  `validate_actions()` without also checking `VOCABULARY_DOC` can silently
  make the two disagree (the LLM would then be told about capabilities the
  validator doesn't allow, or vice versa) — no automated check enforces this
  today.
- `context="grasp"` is the only context implemented; if a future step type
  needs a different closing invariant (e.g. an "release-only" step with no
  gripper-close requirement), `validate_actions()`'s `context` parameter is
  the extension point, not a new function.
- This resolves PRD open question 3. The adapter gap from
  [ADR 0010](./0010-robot-control-integration.md) is still open — plan-driven
  runs with `ACTION_SYNTHESIS=llm` validate and execute against
  `MovementClient` exactly as the scripted path does, which means they are
  equally blocked from driving the **real** arm until that adapter is
  written; sim/mock runs exercise the full guardrail path today (see
  `factory.py`'s `dry_run` wiring: `MockPlanProvider` + `MockActionSynthesizer`).
