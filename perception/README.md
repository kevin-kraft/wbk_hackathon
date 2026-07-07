# Perception module

Three inference microservices — **YOLO**, **SAM3**, **LocateAnything** — each a
FastAPI app, all running in **one CUDA container** under `supervisord`. This is
the vision layer of the disassembly system. See [`../docs/architecture.md`](../docs/architecture.md)
for the full picture.

| Service | Port | Endpoint |
|---|---|---|
| yolo | 8001 | `POST /infer` — object detection |
| sam3 | 8002 | `POST /infer` — promptable segmentation |
| locateanything | 8003 | `POST /infer` — text-prompted localization |

Each also serves `GET /health`, `GET /` (info), and `GET /docs` (OpenAPI UI).

## Run

```bash
# from repo root — builds the image and starts all three services on the GPU
docker compose up --build perception
```

Then, e.g.:

```bash
# base64-encode an image and hit the YOLO service
IMG=$(base64 -w0 test.jpg)
curl -s localhost:8001/infer -H 'content-type: application/json' \
  -d "{\"image_b64\": \"$IMG\", \"conf\": 0.25}" | jq
```

Requires the **NVIDIA Container Toolkit** on the host. To run CPU-only (e.g. on a
laptop, for the mock/dev path), set `PERCEPTION_DEVICE=cpu`.

## Local dev (without Docker)

```bash
uv venv && uv pip install -r requirements.txt
uvicorn services.yolo.main:app --port 8001 --reload           # run one service
# or all three via supervisor:
supervisord -c supervisord.conf
```

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `PERCEPTION_DEVICE` | `cuda` | `cuda` \| `cpu` \| `cuda:0` — falls back to CPU if CUDA absent |
| `WEIGHTS_DIR` | `/weights` | Local checkpoint directory (mounted in compose) |
| `YOLO_WEIGHTS` | `yolo11n.pt` | YOLO checkpoint (name auto-downloads, or a path in `WEIGHTS_DIR`) |
| `SAM3_MODEL_ID` / `SAM3_WEIGHTS` | — | SAM3 backend id / checkpoint |
| `LOCATE_MODEL_ID` / `LOCATE_WEIGHTS` | — | LocateAnything backend id / checkpoint |

## Layout

```
services/
  shared/          schemas · imaging · config · model_base · app_factory
  yolo/            model.py (Ultralytics)  +  main.py  (:8001)
  sam3/            model.py                +  main.py  (:8002)
  locateanything/  model.py                +  main.py  (:8003)
```

Each service is intentionally self-contained (own `model.py`, `main.py`,
`requirements.txt`) so it can be extracted into its own container later.

## Adding a model / service

1. Subclass `BasePerceptionModel` in a new `services/<name>/model.py` (implement
   `load()` and `infer()`).
2. Add `services/<name>/main.py` using `create_service_app(...)` + a typed
   `/infer` route.
3. Add request/response types to `services/shared/schemas.py`.
4. Register a `[program:<name>]` block in `supervisord.conf` and a port in the
   Dockerfile / compose.

## Status

- **yolo** — Ultralytics YOLO, ready to run.
- **sam3** — Meta SAM 3 via `transformers` (`facebook/sam3`). Text/concept prompts
  and point/box prompts both wired. Weights are gated on HuggingFace but are
  **already cached locally** on this machine, so the service loads them offline.
- **locateanything** — NVIDIA `LocateAnything-3B` via `trust_remote_code`. Text
  query → boxes/points; scores are rank-derived (no native confidence). Weights
  **pre-fetched** into the local HF cache — loads offline.

Both caches live in `~/.cache/huggingface`, which `docker-compose.yml` mounts
into the container.
