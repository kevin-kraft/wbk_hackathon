# ADR 0005: Mock-first, interface-seam integration for the orchestrator

## Related Docs
- [System: Orchestrator](../System/orchestrator.md) — the module this decision shapes: loop, Protocol seam, entry points
- [System: Architecture](../System/architecture.md) — where the orchestrator sits in the overall pipeline
- [SOP: running the orchestrator dry-run](../SOP/running_orchestrator_dry_run.md)

## Status

Accepted (commit `3abc923`, 2026-07-07).

## Context

By the time the orchestrator (the state-machine that runs the full
disassembly loop) needed to be built, three pieces of the pipeline were not
yet available:

- YOLO detection weights/tuning (perception stage exists as scaffolding, but
  the specific detection behavior the loop depends on was still moving).
- The **Jetson arm movement endpoint** — owned by a teammate, hardware-gated.
- The **binary grip (pressure) sensor** — also teammate-owned hardware.

This is a hackathon: the team needed to be able to build, test, and **demo
the entire loop** — including the "rectify grabbing mistakes" retry logic
that is one of the three core product jobs — without waiting for hardware or
a teammate's endpoint to land, and without the loop's own logic and tests
being blocked on external dependencies outside this repo's control.

## Decision

The orchestrator (`orchestrator/loop.py`) depends **only on Protocol
interfaces** (`orchestrator/clients/base.py`) — `SceneCamera`,
`PerceptionClient`, `PoseClient`, `GraspPlanner`, `MovementClient`,
`GripSensor`, `InspectionCamera`, `DamageClient`. It never imports a concrete
HTTP client or a concrete piece of hardware directly.

Two implementations exist for every Protocol from day one:

1. **Mocks** (`orchestrator/mocks.py`) — deterministic, parameterized
   in-memory stand-ins (e.g. `MockGrip(fail_first=True)` to force the
   rectify-retry path, `MockDamage(damaged_classes={...})` to force the
   reject-bin path). These power both `python -m orchestrator.dry_run` (a
   full narrated run, no services/GPU/hardware) and the test suite
   (`tests/orchestrator/test_loop.py`).
2. **Real clients** (`orchestrator/clients/http_*.py`, `cameras.py`,
   `naive_grasp.py`) — talk to the actual services (perception/pose/damage,
   already built in this repo) or the external teammate-owned endpoints.

`orchestrator/factory.py`'s `build_orchestrator(dry_run: bool)` is the single
switch point between the two; the real-client imports are lazy specifically
so that the dry-run and the test suite never require `httpx`/`cv2`/`numpy`
to be installed.

For the two endpoints this repo doesn't own (Jetson movement, grip sensor),
the real HTTP clients (`HttpMovement`, `HttpGrip`) were written against
**proposed contracts** (`contracts/movement_api.md`, `contracts/grip_api.md`)
authored *by* this repo and handed to the hardware teammates, rather than
waiting to see what they'd ship first. Both contract docs say explicitly
that the hardware side may adjust the shape and the client will follow.

Similarly, real grasp planning isn't built yet — `NaiveTopDownGrasp`
(`orchestrator/clients/naive_grasp.py`) is a deliberately naive top-down
placeholder behind the `GraspPlanner` Protocol, present so the loop is
complete end-to-end today.

## Consequences

- **The full loop runs and is demoable today**, including the rectify-retry
  behavior, entirely on mocks — proven by `tests/orchestrator/test_loop.py`
  (5 tests) and `python -m orchestrator.dry_run`. This decoupled "does the
  state machine work" from "is the hardware ready."
- **Swapping in a real client is a one-line change at the composition root**
  (`factory.py`), not a change to `loop.py`. When YOLO tuning lands, the
  Jetson endpoint comes online, or the grip sensor is wired up, only the
  corresponding client file (or `dry_run` flag) changes.
- **The proposed contracts are a coordination tool, not a spec dictated to
  teammates.** They exist so integration work (the `Http*` client code) could
  start in parallel with hardware work, at the cost that the contracts may
  still shift once the hardware teammates push back — the `Http*` clients
  will need to track that if/when it happens.
- **Update (2026-07-07):** the REST-contract bet paid off — a hardware
  teammate confirmed the movement/grip interface will be an HTTP-adapter
  microservice wrapping NeuraPy (NEURA's SDK), landing in this repo shortly.
  An earlier inspection of the Jetson controller had found NeuraPy exposed
  with no REST API of its own, which had cast doubt on the `HttpMovement`/
  `HttpGrip` approach; that doubt is now resolved and the existing clients/
  contracts remain the integration target. See
  [System: Orchestrator](../System/orchestrator.md) "Teammate-owned
  contracts" for the detail.
- **The naive grasp planner and the two external endpoints are known,
  tracked placeholders** — see [System: Orchestrator](../System/orchestrator.md)
  "Teammate-owned contracts" and "Not yet built" in
  [System: Architecture](../System/architecture.md). Do not treat
  `NaiveTopDownGrasp`, the Jetson movement contract, or the grip contract as
  final/production-ready.
- Test cost is low: the whole orchestrator test suite runs with **no**
  GPU, network, or hardware, keeping it fast and CI-friendly (same
  no-GPU/no-network property the perception/pose/damage tests already have —
  see [SOP: running the tests](../SOP/running_tests.md)).

## Alternatives considered

- **Wait for hardware/endpoints before building the loop.** Rejected — would
  have blocked all orchestrator development and the demo on external,
  uncontrolled timelines during a time-boxed hackathon.
- **Stub the two external endpoints with hardcoded fixed responses inside
  `loop.py` itself** (no Protocol layer). Rejected — would require editing
  the state machine itself to switch from mock to real behavior, mixing
  test/demo concerns into production logic, and would not naturally support
  parameterized mock scenarios (fail-first grip, damaged-class routing) that
  the tests rely on.
