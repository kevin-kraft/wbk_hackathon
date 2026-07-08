# PRD — ERP-driven, LLM-orchestrated disassembly plan

Status: **implemented (2026-07-08).** All four pieces described below are
built and tested (204 pytest tests, 30 frontend Vitest tests, `npm run build`
clean). Recorded as vision-only on 2026-07-08; implemented the same day. See
[System: Orchestrator](../../System/orchestrator.md) "Plan mode" for the
current-state reference — this file is kept for provenance (why each piece
was scoped the way it was) rather than as the implementation's source of
truth.

## Related Docs
- [System: Architecture](../../System/architecture.md) — the pipeline this extends (perception → pose → grasp → movement → grip → damage), now with the planning head
- [System: Orchestrator](../../System/orchestrator.md) — `_run_planned`/`_run_fixed`, the `PlanProvider`/`ActionSynthesizer` Protocols, the new `PLAN_GENERATED`/`STEP`/`GUARDRAIL` events
- [Integration Points & Wire Contracts](../../System/integration_points.md) — the perception/pose wire contracts step 2 reuses as-is
- [Decisions/0003 — damage fail-safe sort policy](../../Decisions/0003-damage-failsafe-sort-policy.md) — the existing OK/reject bin-sort logic step 4 reuses unchanged
- [Decisions/0010 — robot_control integration](../../Decisions/0010-robot-control-integration.md) — the movement-adapter gap that still blocks any generated plan (LLM- or static-sourced) from driving the **real** arm
- [Decisions/0011 — LLM action selector, constrained vocabulary](../../Decisions/0011-llm-action-selector-constrained-vocabulary.md) — resolves open question 3 below
- `orchestrator/clients/erp.py`, `orchestrator/clients/llm_planner.py`, `orchestrator/actions.py`, `orchestrator/clients/llm_actions.py` — the implementation

## What this is

A vision for extending the pipeline with an ERP-driven planning head and an
LLM-mediated execution loop, replacing the orchestrator's fixed hardcoded
stage sequencing with a **generated, per-part plan** that is then executed
step by step. Four parts, as articulated by the team — each annotated below
with what shipped:

### 1. New head-of-pipeline module — ERP part selection + LLM plan generation

An operator selects the correct part/product on the station in an ERP
system. An LLM reads the ERP data for that part and generates an **ordered
disassembly plan**: a sequence of steps like "first take off part A using
action X, then disassemble part B by performing action Y."

**Shipped.** `orchestrator/data/erp_products.json` is the mock ERP dataset
(`{products: {id: {name, description, parts: [{part, action, notes}]}}}`,
overridable via `ERP_PRODUCTS_PATH`). `StaticPlanProvider`
(`orchestrator/clients/erp.py`) turns an entry into a `Plan` in ERP order,
stdlib only. `LlmPlanProvider` (`orchestrator/clients/llm_planner.py`) asks
an LLM (via OpenRouter) to re-order and describe the same parts; the
`PlanProvider` Protocol (`orchestrator/clients/base.py`) is the seam a real
ERP client would implement with no loop changes, matching ADR 0005's
mock-first pattern. `GET /products` (`orchestrator/app.py`) lists the
selectable products for the dashboard's `ProductSelector`.

### 2. Orchestrator consumes the plan step by step, queries perception + pose per step

For each step in the generated plan, the orchestrator queries the existing
detection/segmentation/6DoF-pose endpoints for that step's specific part and
obtains its exact position.

**Shipped, unchanged machinery.** `_run_planned()` (`orchestrator/loop.py`)
drives the plan; per step it calls the new `PerceptionClient.locate(frame,
class_name)` (grounds a *named* part, vs. the fixed loop's `next_part` which
*chooses* one) and then the same `_process_part()` shared with fixed mode
(POSE → PLAN → GRASP → REMOVE → INSPECT → SORT — no changes to
pose/segment/is_present or the perception/pose wire contracts). A step whose
part isn't found in the scene emits `SKIP` and the plan continues (already
removed, or never present); a step that fails grasping after
`max_grasp_attempts` `BLOCKS` the whole run, because ordered disassembly
means later parts may be physically under the stuck one.

### 3. LLM synthesizes arm commands from instruction + 6DoF pose + movement-API docs

An LLM takes three inputs — the step's instruction, the part's 6DoF pose,
and the movement-API documentation — and generates a command or sequence of
commands for the arm to perform the disassembly action.

**Shipped, with the safety-critical open question resolved narrowly, not
broadly.** `LlmActionSynthesizer` (`orchestrator/clients/llm_actions.py`)
is the `ActionSynthesizer` Protocol implementation; its "movement-API docs"
input is `orchestrator/actions.py`'s `VOCABULARY_DOC`, not the full
`contracts/movement_api.md` — the LLM selects from a small closed action
vocabulary (named poses + pose references, never coordinates), validated
deterministically by `validate_actions()` before anything reaches a
`MovementClient`, with `scripted_grasp_sequence()` (identical motion to the
original loop) as the fallback on any violation. See
[ADR 0011](../../Decisions/0011-llm-action-selector-constrained-vocabulary.md)
for the full decision and the alternatives that were rejected. This is
**opt-in** (`ACTION_SYNTHESIS=llm`; default `scripted` never touches an LLM
in the motion path at all).

### 4. Post-removal: secondary-camera fault check + OK/reject sort

After detaching a part, the arm holds it into the secondary camera; a VLM
checks it for faults/damage; the part is then sorted into an OK bin or
reject (not-OK) bin.

**Unchanged, as anticipated.** `_process_part()`'s `INSPECT`/`SORT` tail is
identical in fixed and plan mode — `damage.inspect()` and the fail-closed
bin-sort policy (ADR 0003) are reused verbatim; the plan doesn't touch this
stage at all.

## What is genuinely new (summary, resolved)

| Piece | Status | Notes |
|---|---|---|
| (a) ERP selection + LLM plan generation | **Shipped** | Mock-ERP JSON behind `PlanProvider`; `StaticPlanProvider` + `LlmPlanProvider` (OpenRouter, permutation-validated, static-fallback on any error) |
| (b) LLM command synthesis per step | **Shipped, opt-in** | Constrained vocabulary + deterministic validation + scripted fallback (ADR 0011); `ACTION_SYNTHESIS=llm\|scripted` |
| (c) Orchestrator executes a generated plan instead of one fixed pipeline | **Shipped** | `run(product=...)` dispatches to `_run_planned`; `_run_fixed` (original behavior) untouched and still the default with no `product` |

## Open questions — resolutions

1. **LLM/provider choice.** **Resolved: reuse OpenRouter.**
   `orchestrator/clients/openrouter.py` mirrors `damage/client.py`'s pattern
   (same env-var family: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`; new
   `PLANNER_MODEL` covers both plan generation and action synthesis). Kept
   local to the orchestrator package rather than importing `damage/`,
   consistent with this repo's copy-per-service convention (e.g. `auth.py`,
   per ADR 0009/0010).
2. **ERP scope for the hackathon.** **Resolved: mocked, static JSON, behind
   the `PlanProvider` Protocol.** `orchestrator/data/erp_products.json`
   ships in the image; a real ERP client can drop in later implementing the
   same Protocol with no loop changes — the same mock-first play as every
   other teammate-owned seam (ADR 0005).
3. **Guardrails on LLM-generated movement commands.** **Resolved: constrained
   action vocabulary + deterministic validation + scripted fallback.** See
   [ADR 0011](../../Decisions/0011-llm-action-selector-constrained-vocabulary.md)
   for the full decision; alternatives (free-form matrices, schema-only
   validation without pose indirection) were explicitly rejected because the
   pose numbers themselves must never be model-authored.
4. **Plan-step ↔ orchestrator state-model mapping.** **Resolved: the plan
   replaces the sequencer only** — `LOCATE`/`POSE`/`INSPECT`/`SORT` machinery
   is unchanged between fixed and plan mode; only "what determines the next
   part" changes (`perception.next_part()` vs. a plan step +
   `perception.locate()`). Two new `LoopEvent` states were added rather than
   overloading existing ones: `PLAN_GENERATED` (once, carries the full plan)
   and `STEP` (per plan-step narration, `index`/`total`/`action`); `GUARDRAIL`
   was added separately for the action-synthesis fallback path (open
   question 3, not this question, but landed at the same time).

## Remaining prerequisite — not resolved by this work

[ADR 0010](../../Decisions/0010-robot-control-integration.md)'s
orchestrator↔movement adapter gap is **still open**: `HttpMovement` cannot
yet drive `robot_control/`'s real API. This means plan-driven runs —
whether the plan is LLM- or statically-sourced, and whether actions are
LLM-synthesized or scripted — are equally blocked from moving the **real**
arm today. Everything above is fully exercised against mocks/dry-run
(`factory.py`'s `dry_run` wiring: `MockPlanProvider` + `MockActionSynthesizer`
drive the full validate→execute guardrail path) and will work against a real
plan-driven run the moment the movement adapter lands — no further changes
to the planning/action-synthesis code are anticipated for that to happen.

## Non-goals / explicitly not decided here

This document intentionally does not specify request/response schemas beyond
what's implemented, a rollout sequence, or UI beyond what shipped
(`ProductSelector`, `PlanProgress` — see
[System: Dashboard](../../System/dashboard.md)).
