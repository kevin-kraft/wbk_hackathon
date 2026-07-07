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

### Newer GPUs (Blackwell / sm_120)

The default base image (`pytorch/pytorch:2.5.1-cuda12.4`) predates Blackwell and
**won't run** on RTX PRO 6000 / RTX 50-series GPUs. Build against a CUDA 12.8 /
torch 2.8 base via the `BASE_IMAGE` build-arg:

```bash
docker build --build-arg BASE_IMAGE=pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel \
  -t wbk-perception:blackwell perception/
```

`requirements.txt` deliberately omits torch, so the base image's torch is used as-is.

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

## Deploying to a remote GPU server

For a server without HF auth (and to skip re-downloading gated SAM 3), `rsync` the
local model dirs into a server-side cache and mount it, instead of downloading:

```bash
rsync -a ~/.cache/huggingface/hub/models--facebook--sam3 \
        ~/.cache/huggingface/hub/models--nvidia--LocateAnything-3B \
        <server>:hf-cache/hub/
docker run -d --gpus '"device=1"' \
  -p 127.0.0.1:6767:8001 -p 127.0.0.1:6768:8002 -p 127.0.0.1:6769:8003 \
  -v ~/hf-cache:/root/.cache/huggingface -e WBK_API_TOKEN=... wbk-perception:blackwell
```

Bind to `127.0.0.1` and reach it from elsewhere over an SSH tunnel
(`ssh -L 8001:localhost:6767 …`) rather than exposing the ports. On a shared
server (single account / shared Docker daemon) there is no real isolation from
other tenants — keep secrets (e.g. the OpenRouter key) off the box.
