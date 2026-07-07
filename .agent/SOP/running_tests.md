# SOP: Running the tests

## Related Docs
- [Architecture](../System/architecture.md) — test suite summary
- [Integration Points](../System/integration_points.md) — why deferred imports let this suite run without GPU/torch
- [SOP: running the services](./running_services.md)

## Run

```bash
uv sync            # installs the light dev deps (pytest, pillow, numpy, opencv-python-headless, pydantic, fastapi, httpx) into .venv
uv run pytest      # whole suite (81 tests as of this scan)
uv run pytest -q tests/damage   # just one module's tests
```

No GPU, model weights, `OPENROUTER_API_KEY`, or network access required — this
is a deliberate property of the suite (see below), not an accident of what
happens to be mocked today.

This project is managed with `uv` (per `pyproject.toml`,
`[dependency-groups].dev`) — do not `pip install` into the system Python or
hand-roll a venv here.

## CI

`.github/workflows/tests.yml` runs on push/PR to `main`: installs `uv`
(`astral-sh/setup-uv@v5`), then `uv sync --frozen && uv run pytest -q`. It
deliberately uses the light `dev` dependency group only — the suite never
needs torch/transformers/ultralytics, so CI stays fast and doesn't need a
GPU runner.

## Why this works without GPU/network: the conftest.py import-root split

`tests/conftest.py` adds three sibling roots to `sys.path`, because this
monorepo has **three different runtime import roots at deploy time** and the
test suite needs to be able to import all three simultaneously:

| Stage | Runtime import root | Why (see supervisord.conf / Dockerfiles) |
|---|---|---|
| `damage/` | repo root | run as package `damage` (`damage/__init__.py` exists) |
| `perception/` | `perception/` itself | `uvicorn services.<name>.main:app`, cwd=`/app/perception` |
| `pose/` | `pose/` itself | each container sets `PYTHONPATH=/svc`, copies `shared/` + `<name>_svc/` |

None of the three roots collide on a top-level module name (`damage` vs.
`services` vs. `shared`/`foundationpose_svc`/`gigapose_svc`), so all three can
be on `sys.path` at once — that's the whole trick. **If you add a new
top-level module/package to any stage, check it doesn't collide with a
sibling's top-level name**, or the conftest's assumption breaks.

The other half of the trick: every adapter defers its heavy ML imports
(`torch`, `transformers`, `ultralytics`, `nvdiffrast`, the FoundationPose/
GigaPose repo modules) to inside `load()`/`infer()`/`estimate()` — never at
module top-level. Tests only reach code paths above that line, or monkeypatch
the adapter instance entirely for FastAPI route smoke tests. **Keep new
adapter code following this pattern** — a top-level `import torch` in any
`model.py` will break every test that imports that module, even indirectly.

## Layout

```
tests/
  conftest.py                     sys.path bootstrap (see table above)
  perception/
    test_imaging.py               services/shared/imaging.py
    test_config.py                services/shared/config.py (Settings, resolve_device)
    test_schemas.py                services/shared/schemas.py request defaults
    test_locateanything_parse.py   LocateAnythingBackend._parse() token parser
    test_app_smoke.py              FastAPI TestClient smoke tests (model mocked)
  pose/
    test_imaging.py                shared/imaging.py (rgb/depth/mask/K decode)
    test_schemas.py                 shared/schemas.py `class`-alias round trip
    test_app_smoke.py              FastAPI TestClient smoke tests (runner mocked)
  damage/
    test_client.py                  client._extract_json + call_openrouter errors
    test_prompts.py                 prompts.build_messages ordering/shape
    test_reference.py               reference.load_reference disk loader
    test_app.py                     /inspect bin-sorting policy (call_openrouter mocked)
```

## What's intentionally NOT covered

`YoloModel.load/infer`, `Sam3Backend.load/infer`, `LocateAnythingBackend.load`,
`FoundationPoseRunner.load/estimate`, `GigaPoseRunner.load/estimate` — these
require real weights and a GPU stack and are out of scope for a fast unit
suite. The FastAPI smoke tests cover the route wiring around them by
monkeypatching the adapter instance. Do not add tests here that secretly need
a GPU or network — that breaks the CI contract this suite is built on.
