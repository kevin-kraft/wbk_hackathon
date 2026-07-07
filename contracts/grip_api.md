# Proposed contract — grip (grab-detection) sensor endpoint

*Draft for the hardware/grip teammate — adjust freely; the orchestrator's
`HttpGrip` client will follow.*

Base URL via `GRIP_URL` (default `http://jetson.local:9001`).

## Approach: motor-current grip sensing

Grip force is approximated from the **current through the gripper motor** (current
∝ torque ∝ clamping force) — an analog upgrade over a binary 0/1 pad sensor. Keep
the derived **boolean authoritative and fast** for the loop, but also expose the
**raw analog value** so richer partial/wrong-grip checks can use it later.

## `GET /grip`

```jsonc
// preferred — boolean + analog
{
  "grasped": true,     // derived: current above the "holding" threshold
                       //   (AND, if available, gripper NOT fully closed — see pitfall)
  "current": 0.82,     // motor current, amps, STEADY-STATE / stall
  "width": 0.031,      // gripper opening in metres, if the gripper reports position
  "threshold": 0.5     // optional: the current threshold used to derive `grasped`
}
```

Boolean-only forms still work with the client: `{ "grasped": true }` or `{ "raw": 1 }`.

- The orchestrator polls this **right after closing the gripper**. `grasped:false`
  triggers the rectify path: release, re-plan the grasp, retry (up to
  `MAX_GRASP_ATTEMPTS`).

## ⚠️ The end-stop pitfall (please design around this)

Motor current **alone can false-positive**: closing on **nothing** runs the
gripper to its mechanical end-stop, where the motor **also stalls at high
current** — looking just like a firm grip. Disambiguate with gripper
**position/width**:

| case | width | current |
|---|---|---|
| object held | stalls at a **partial** opening (> fully-closed) | elevated |
| empty | reaches **fully closed** (≈ min) | elevated (end-stop) |

**If the gripper reports position, expose `width`** — it cleanly separates the two.
Without position feedback, fall back to a current-vs-time profile or a per-part
expected width, and flag this as a real limitation.

## Timing

Read **steady-state / stall** current, *after* the gripper has finished closing —
not the inrush/acceleration transient. The movement `/gripper` close call is
synchronous (blocks until the motion settles, see `movement_api.md`), so the
`/grip` read that follows is expected to be settled. If close can return before
stall, add a short settle on the sensor side before sampling.

## Calibration

- Baseline **closing-on-nothing** current curve + the **fully-closed** width.
- "Holding" threshold: above free-run current, below end-stop stall.
- Optional **per-part expected current band** — a part gripped too weakly
  (slipping) or a wrong/too-small part reads low; this is how the analog signal
  catches partial/wrong grips the old 0/1 never could.

## How this maps to the pipeline

- Fast boolean → the orchestrator's grip-verify/rectify gate (built now).
- `current` + `width` → future **partial/wrong-grip** check — complementary to the
  deferred **VLM grip verifier**, which still adds the semantic/geometric "is it
  the RIGHT part, gripped squarely" judgment the current signal can't give.

## Notes

- Debounce/filter the raw current on the hardware side; the orchestrator takes the
  boolean at face value.
- Optional `GET /grip/raw` → richer telemetry (per-sample current, or per-pad array
  if multiple sensors) for tuning/logging.
