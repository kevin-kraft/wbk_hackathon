# ADR 0007: Motor-current-based grip sensing (not a binary pad)

## Related Docs
- [System: Orchestrator](../System/orchestrator.md) — "Teammate-owned contracts" section, updated `contracts/grip_api.md` summary
- [ADR: mock-first, interface-seam integration](./0005-mock-first-interface-seam-integration.md) — why this change required no `loop.py`/Protocol changes
- `contracts/grip_api.md` (in-repo) — the full contract this ADR justifies
- `contracts/movement_api.md` (in-repo) — the companion blocking-close requirement

## Status

Accepted (commit `e0a1b13`, 2026-07-07).

## Context

The original grip contract (drafted alongside
[ADR 0005](./0005-mock-first-interface-seam-integration.md)) assumed a
binary 0/1 pressure-pad sensor: `GET /grip` returning `{"grasped": bool}` or
`{"raw": 0|1}`, polled once right after the gripper closes, gating
`_grasp_with_retry`'s rectify logic.

The actual gripper hardware the teammate is integrating does not expose a
dedicated pressure pad — it exposes **motor current** telemetry only. Motor
current is a reasonable proxy for grip force (current ∝ torque ∝ clamping
force), but it is not a clean binary signal: closing the gripper on
**nothing** drives it to its mechanical end-stop, where the motor **also**
stalls at high current — indistinguishable from a firm grip by current
alone.

## Decision

Redesign `contracts/grip_api.md` around the current-based signal instead of
waiting for different hardware:

- `GET /grip` returns a **derived boolean** `grasped` (current above a
  calibrated "holding" threshold) **plus** the raw analog values: `current`
  (amps, steady-state/stall reading) and, if the gripper reports position,
  `width` (opening in metres). `threshold` is optionally echoed for
  debugging. Boolean-only responses (`{"grasped": bool}` / `{"raw": 0|1}`)
  remain accepted for backward compatibility.
- The **boolean stays authoritative** for the orchestrator's rectify gate —
  `GripSensor.is_grasped()` and `_grasp_with_retry`'s logic in `loop.py` are
  **unchanged**. Only the hardware-side derivation of that boolean changes.
- The **end-stop pitfall is documented explicitly** as a design constraint
  the hardware side must account for: disambiguate "held" from "empty/at
  end-stop" using gripper **width** (object held → stalls at a *partial*
  opening; empty → reaches *fully closed*). Without position feedback, the
  contract calls out falling back to a current-vs-time profile or a
  per-part expected current band as a known, real limitation — not silently
  ignored.
- **Read timing is steady-state, not inrush.** The current reading must be
  taken *after* the gripper finishes closing (post-stall), not during the
  initial acceleration transient. `contracts/movement_api.md`'s `/gripper`
  close call was updated in the same commit to require blocking until the
  gripper settles/stalls, so the `/grip` read that immediately follows is
  guaranteed valid.
- The analog `current`/`width` values are earmarked as future inputs to a
  **partial/wrong-grip check**, complementary to (not a replacement for) the
  still-deferred **VLM grip verifier** (see [System:
  Orchestrator](../System/orchestrator.md), "Two future VLM roles") — the
  current signal can catch a weak/slipping grasp, but not "grasped the
  wrong part cleanly."

## Consequences

- **No `orchestrator/loop.py` or Protocol changes were needed** — the
  `GripSensor` Protocol and `HttpGrip` client absorb the new response shape
  without touching the state machine. This is the Protocol-seam design
  ([ADR 0005](./0005-mock-first-interface-seam-integration.md)) paying off
  exactly as intended: the contract changed, the consumer didn't.
- Grippers **without** position/width feedback have a real, acknowledged
  gap: they cannot reliably tell "held" from "end-stop" using current alone
  and must fall back to a coarser heuristic (current-vs-time profile,
  per-part expected current band). Anyone debugging a grip false-positive
  should check whether `width` is populated before trusting `grasped` alone.
  This is the single most important operational gotcha in this contract —
  future grip-sensor debugging should start here.
- The analog signal is a **stepping stone, not a substitute**, for the
  deferred VLM grip verifier — it narrows (but does not close) the gap the
  old binary sensor left, per the "Two future VLM roles" note in
  [System: Orchestrator](../System/orchestrator.md).
- The blocking-close requirement on `/gripper` (`movement_api.md`) is now a
  **cross-contract dependency**: the grip contract's steady-state read
  assumption only holds if the movement side actually honors it.

## Alternatives considered

- **Wait for a real binary pressure-pad sensor** from the hardware
  teammate: rejected — would block the "rectify grabbing mistakes" product
  goal on hardware the team doesn't control, at hackathon time scale.
- **Treat any nonzero current as `grasped=true`** (no threshold, no width):
  rejected outright — this is exactly the end-stop false positive; every
  empty close would register as a successful grasp.
- **Add dedicated force/position sensing hardware** instead of reusing
  existing motor-current telemetry: rejected as out of scope/budget for a
  hackathon — motor current was already available for free from the
  gripper driver, whereas new sensing hardware would need procurement and
  integration time the team didn't have.
