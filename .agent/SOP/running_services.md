# SOP: Running the services

## Related Docs
- [Architecture](../System/architecture.md) — what each service does and its port
- [Integration Points](../System/integration_points.md) — wire contracts, HF cache mount
- [ADR: perception shared container vs. pose split containers](../Decisions/0001-perception-shared-container-pose-split-containers.md)
- [ADR: pose contract reuses kip-pose-viewer](../Decisions/0004-pose-contract-reuses-kip-pose-viewer.md)
- [SOP: running the tests](./running_tests.md)

All commands below run from the repo root (`/home/yannic/code/wbk-hackerthon`)
unless noted. Everything is driven by the single `docker-compose.yml`.

## Prerequisites

- **Perception and pose need an NVIDIA GPU + NVIDIA Container Toolkit** on the
  host (`docker-compose.yml` reserves `driver: nvidia, capabilities: [gpu]`
  for those services). Damage is CPU-only.
- **Perception**: SAM 3 weights (`facebook/sam3`) are gated on HuggingFace —
  request access on the model page, then `hf auth login` (or set `HF_TOKEN`
  in the environment) *before* the first `docker compose up --build
  perception`, or the `sam3` process will fail to load at startup.
- **Damage**: an OpenRouter API key (`OPENROUTER_API_KEY`).
- **Pose**: the two GPU base images must be built first — see below. They are
  not on any registry; they're built locally from sibling model repos.

## 1. Perception (yolo + sam3 + locateanything)

```bash
docker compose up --build perception
```

This builds one image from `perception/Dockerfile` (base:
`pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`) and runs all three services
under `supervisord` inside it, exposing `:8001` (yolo), `:8002` (sam3),
`:8003` (locateanything).

Weights: the compose file mounts `hf-cache:/root/.cache/huggingface` (a named
volume) and `./weights:/weights` (bind mount, `WEIGHTS_DIR=/weights`). Per the
task brief for this scan, SAM 3 weights are **already cached** and
LocateAnything-3B has been **pre-fetched** into the mounted HF cache — a fresh
environment without that cache populated will pull both on first load, which
is slow and, for SAM 3, requires the gated-access step above first.

To run perception CPU-only (e.g. a laptop, dev/mock path):
`PERCEPTION_DEVICE=cpu docker compose up --build perception` — `resolve_device()`
in `perception/services/shared/config.py` falls back to CPU automatically if
CUDA is unavailable even without setting this, but setting it explicitly skips
the CUDA probe.

Smoke-test one service:
```bash
IMG=$(base64 -w0 test.jpg)
curl -s localhost:8001/infer -H 'content-type: application/json' \
  -d "{\"image_b64\": \"$IMG\", \"conf\": 0.25}" | jq
```

Local dev without Docker:
```bash
cd perception
uv venv && uv pip install -r requirements.txt
uvicorn services.yolo.main:app --port 8001 --reload      # one service
# or, all three:
supervisord -c supervisord.conf
```

## 2. 6DoF pose (foundationpose + gigapose)

**The two GPU base images must be built first**, from the model repos
(outside this repo, under `~/code/`). These compile CUDA extensions — slow,
and GPU-architecture-specific (the reference Dockerfiles target Blackwell /
`sm_120`; retag / change `TORCH_CUDA_ARCH_LIST` for a different GPU):

```bash
docker build -t foundationpose:blackwell -f ~/code/FoundationPose/docker/Dockerfile.blackwell ~/code/FoundationPose
docker build -t gigapose:blackwell        -f ~/code/GigaPose/docker/Dockerfile.blackwell        ~/code/GigaPose
```

Then build and run the two service containers:

```bash
docker compose up --build foundationpose gigapose
```

`foundationpose_svc/Dockerfile` and `gigapose_svc/Dockerfile` each build `FROM`
the corresponding base image and only add FastAPI + the thin service layer —
see [ADR 0001](../Decisions/0001-perception-shared-container-pose-split-containers.md)
for why these cannot be one image.

The compose file mounts the actual model repos into the containers
(`${FOUNDATIONPOSE_REPO:-~/code/FoundationPose}:/workspace/FoundationPose`,
`${GIGAPOSE_REPO:-~/code/GigaPose}:/workspace/GigaPose`) — override those env
vars if the repos live elsewhere. `./pose/assets/meshes` is mounted for
FoundationPose CAD meshes.

**Per-object assets you must supply before poses will be correct** for your
actual disassembly parts (the reference KIP project hardcodes two demo
parts):
- **FoundationPose** — a `.obj` CAD mesh per class, **in metres**, in
  `FP_MESH_DIR` (`./pose/assets/meshes`), plus a `FP_CLASS_MESH` JSON map env
  var, e.g. `{"housing":"housing.obj","bracket":"bracket.obj"}`.
- **GigaPose** — a CAD mesh per class **and 162 pre-rendered templates per
  object** on disk before the service starts, rendered via GigaPose's own
  `render_custom_templates.py`. The class→objId map lives in the KIP
  `gigapose_infer` adapter (outside this repo).

Key env vars (full table in `pose/README.md`): `FP_REPO`, `FP_MESH_DIR`,
`FP_CLASS_MESH`, `FP_ITERATIONS` (foundationpose); `GIGAPOSE_REPO`,
`GP_DATASET` (default `kip2`), `GP_ENABLE_REFINER` (gigapose).

Known fragile bits: FoundationPose is ~2s/instance and serial (shared
non-thread-safe GL context) — cap instances via the caller's `top_n`; depth
must be exact metric uint16 mm; GigaPose templates must be correctly scaled
or coarse matching silently degrades.

## 3. Damage inspection (OpenRouter VLM, CPU)

```bash
export OPENROUTER_API_KEY=sk-or-...
docker compose up --build damage
```

Reference images (few-shot known-good/known-damaged examples) can be supplied
two ways, and they combine:
1. Inline in the request (`reference_ok_b64`/`reference_damaged_b64`).
2. On disk, mounted at `REFERENCE_DIR` (compose mounts `./damage/reference:/reference`),
   laid out as `<REFERENCE_DIR>/<part_class>/ok/*.{jpg,png}` and
   `<REFERENCE_DIR>/<part_class>/damaged/*.{jpg,png}`.

Override the model via `OPENROUTER_MODEL` (default `anthropic/claude-sonnet-5`
— must match OpenRouter's model catalog; any vision-capable model works).

Smoke test:
```bash
curl -s localhost:8006/inspect -H 'content-type: application/json' \
  -d '{"images_b64":["'"$(base64 -w0 part.jpg)"'"],"part_class":"housing"}' | jq
```

## Every service, regardless of stage

Exposes `GET /health` and `GET /docs` (OpenAPI UI) in addition to its `POST`
route. Use `/health` to confirm a model finished loading
(`{"status":"ok", "loaded": true, ...}`) before sending real traffic — startup
can take a while for the larger perception/pose models.
