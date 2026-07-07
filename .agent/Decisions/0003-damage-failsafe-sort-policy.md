# ADR 0003: Damage-inspection fail-safe sort policy

## Related Docs
- [Architecture](../System/architecture.md) — damage stage detail
- [Integration Points](../System/integration_points.md) — the `/inspect` contract

## Status
Accepted (as scaffolded, 2026-07-07 — commit `82a88f9`).

## Context

`damage/app.py`'s `/inspect` route asks a VLM (via OpenRouter) to classify a
removed part as `"ok"`, `"damaged"`, or `"uncertain"`, then the arm must place
the part into one of exactly two physical bins: `ok_bin` or `reject_bin`.
Something has to collapse three possible verdicts into two bins.

## Decision

The collapse is hardcoded server-side in `damage/app.py`, not left to the
model:

```python
bin="ok_bin" if verdict == "ok" else "reject_bin"
```

Only a clean `"ok"` verdict routes to `ok_bin`. Both `"damaged"` **and**
`"uncertain"` route to `reject_bin`. The model itself is also constrained
before this line — `damage/app.py` normalizes any verdict string it doesn't
recognize down to `"uncertain"` (`if verdict not in {"ok","damaged","uncertain"}:
verdict = "uncertain"`), so a malformed or unexpected model response also ends
up rejected rather than accepted by default.

## Why

This is a fail-safe / fail-closed design: a false negative (a damaged part
sorted as OK) puts a bad part into the working-parts stream, which is the
costlier failure mode for a disassembly/quality-control pipeline than a false
positive (a good part sorted as reject, i.e. a part needing a second look).
Treating `"uncertain"` as reject rather than as a third bin means the pipeline
never has to build a third physical sorting path, and it means the VLM's own
hedging ("I'm not sure, could be a shadow") can never accidentally let a
damaged part through — the only way to reach `ok_bin` is an unambiguous `"ok"`.

## Consequences

- `reject_bin` will accumulate parts that are actually fine but the model
  wasn't confident about — expect a non-zero false-reject rate by design.
  There is no code path (as of this scan) for a human-in-the-loop re-review
  of `reject_bin` contents; if that's needed it would be a new stage, not a
  policy change here.
- Anyone tuning prompts (`damage/prompts.py`) or swapping the OpenRouter model
  (`OPENROUTER_MODEL` env var) should not expect a change in verdict wording
  to shift the bin logic — the three-way→two-way collapse is fixed in
  `app.py` regardless of prompt changes.
- If a future stage wants finer-grained routing (e.g. a third "needs human
  review" bin), that requires a schema change to `DamageVerdict.bin`'s
  `Literal["ok_bin","reject_bin"]` type in `damage/schemas.py`, not just a
  prompt change.
