# Tests

Unit tests for the pure, verifiable logic in `perception/`, `pose/`, and
`damage/` — schemas, image/tensor codecs, prompt building, the LocateAnything
token parser, and the damage bin-sorting policy. Heavy ML deps (torch,
transformers, ultralytics, nvdiffrast, the FoundationPose/GigaPose repos) are
**never imported**: every place that needs them defers the import inside
`.load()` / `.infer()` / `.estimate()`, and these tests only reach code paths
above that line (or monkeypatch those methods for FastAPI route smoke tests).

## Setup & run

```bash
# from the repo root — installs the light dev deps (pytest, pillow, numpy,
# opencv-python-headless, pydantic, fastapi, httpx) into .venv via uv
uv sync

uv run pytest          # whole suite
uv run pytest -q tests/damage   # just one module's tests
```

No GPU, model weights, `OPENROUTER_API_KEY`, or network access required.

## Layout

Mirrors the three service dirs:

```
tests/
  conftest.py           sys.path bootstrap — see its docstring for why each
                         of perception/, pose/, and the repo root is added
                         (the three dirs each have a different runtime import
                         root; see supervisord.conf / the service Dockerfiles)
  perception/
    test_imaging.py            services/shared/imaging.py
    test_config.py             services/shared/config.py (Settings, resolve_device)
    test_schemas.py             services/shared/schemas.py request defaults
    test_locateanything_parse.py  LocateAnythingBackend._parse() token parser
    test_app_smoke.py          FastAPI TestClient smoke tests (model mocked)
  pose/
    test_imaging.py            shared/imaging.py (rgb/depth/mask/K decode)
    test_schemas.py             shared/schemas.py `class`-alias round trip
    test_app_smoke.py          FastAPI TestClient smoke tests (runner mocked)
  damage/
    test_client.py              client._extract_json + call_openrouter errors
    test_prompts.py             prompts.build_messages ordering/shape
    test_reference.py           reference.load_reference disk loader
    test_app.py                 /inspect bin-sorting policy (call_openrouter mocked)
```

## What's intentionally NOT covered

- `YoloModel.load/infer`, `Sam3Backend.load/infer`, `LocateAnythingBackend.load`,
  `FoundationPoseRunner.load/estimate`, `GigaPoseRunner.load/estimate` — these
  require real weights / a GPU stack and are out of scope for a fast unit
  suite. The FastAPI smoke tests cover the route wiring around them by
  monkeypatching the adapter instance.
