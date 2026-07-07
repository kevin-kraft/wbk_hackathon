# SOP: Running the orchestrator dry-run

## Related Docs
- [System: Orchestrator](../System/orchestrator.md) — loop states, Protocol seam, config
- [ADR: mock-first, interface-seam integration](../Decisions/0005-mock-first-interface-seam-integration.md)
- [SOP: running the services](./running_services.md) — for a real (non-mock) run
- [SOP: running the tests](./running_tests.md)

## When to use this

Use the dry-run to prove or demo the full disassembly loop — including the
grip rectify-retry and the reject-bin path — with **no Docker services, no
GPU, no model weights, and no hardware** required. This is the fastest way to
sanity-check a `loop.py`/`mocks.py`/`factory.py` change before wiring up real
services, and it's what the team uses for the live demo while the Jetson
movement endpoint and grip sensor are still teammate-owned work in progress.

## Run it

From the repo root, with the project's `uv` env synced (see
[SOP: running the tests](./running_tests.md) for `uv sync`):

```bash
uv run python -m orchestrator.dry_run
```

Every stage is mocked (`orchestrator/mocks.py`). The scripted scenario
(`orchestrator/dry_run.py`) deliberately:
- fails the **first** grasp attempt (`MockGrip(fail_first=True)`) so the
  REGRASP/rectify path fires and is visible in the output;
- marks the `"gear"` part as damaged (`MockDamage(damaged_classes={"gear"})`)
  so the reject-bin path is exercised too.

Expected output shape:

```
=== disassembly dry-run (all hardware mocked) ===
[ 1] LOCATE   next part: cover
[ 1] POSE     6DoF pose for cover
[ 1] REGRASP  grasp attempt 1 failed (sensor=0), re-planning
[ 1] GRIP     grasp confirmed (sensor=1) on attempt 2
[ 1] REMOVE   lifted cover clear
[ 1] SORT     cover: ok -> ok_bin
...
[ 4] DONE     assembly fully disassembled
=== summary: {'removed': 3, 'ok_bin': 2, 'reject_bin': 1, 'skipped': 0} ===
```

If the loop, mocks, or event states have changed, this output will change —
update `orchestrator/README.md`'s example block too if so (it carries the
same sample output).

## Running the orchestrator as a service

`docker compose up --build orchestrator` builds `orchestrator/Dockerfile` and
runs `orchestrator.app:app` on `:8000` (see the `orchestrator` entry in
[`docker-compose.yml`](../../docker-compose.yml)). Two ways to call it:

```bash
# mock-driven — same as the dry-run script, over HTTP
curl -s -X POST 'localhost:8000/run?dry_run=true' | jq

# real run — drives the live perception/pose/damage containers plus the
# external Jetson movement + grip-sensor endpoints (MOVEMENT_URL/GRIP_URL)
curl -s -X POST 'localhost:8000/run?dry_run=false' | jq
```

A real run requires perception, pose (foundationpose at minimum — `POSE_URL`
defaults to it), and damage already running (see
[SOP: running the services](./running_services.md)), plus reachable
`MOVEMENT_URL`/`GRIP_URL` endpoints per
[`contracts/movement_api.md`](../../contracts/movement_api.md) and
[`contracts/grip_api.md`](../../contracts/grip_api.md). There is no
"real services, mock hardware" middle mode currently — `dry_run` is
all-mock or all-real (see `orchestrator/factory.py`'s `build_orchestrator`).

## Running just the orchestrator tests

```bash
uv run pytest tests/orchestrator/ -v
```

All 5 tests run on mocks only — no GPU/network/hardware, same as the
dry-run. See [System: Orchestrator](../System/orchestrator.md) "Tests" for
what each test asserts.
