# SOP: Deploying perception to the remote GPU server

## Related Docs
- [Architecture](../System/architecture.md) — Stage 1 Perception (`perception/`), the service/port map
- [Integration Points](../System/integration_points.md) — the HF weight cache mount, the `/infer` contract, shared-token auth
- [System: Training](../System/training.md) — where the deployed weights (`YOLO_WEIGHTS`) come from
- [SOP: running the services](./running_services.md) — the local/single-host `docker compose up perception` path this SOP is an alternative to
- `deploy/README.md` (repo root) — the single-service GHCR deploy model for `orchestrator`/`damage`/`dashboard`; perception and pose are explicitly **not** part of that (built on the GPU server instead, see its table)
- `perception/README.md` — "Newer GPUs (Blackwell / sm_120)" and "Deploying to a remote GPU server" sections; this SOP is the `.agent/`-side pointer to that content plus the wider topology
- Root [`README.md`](../../README.md) "Deployment" — the canonical, current 4-host topology table this SOP's perception slice is part of

## Status: deployed and running, as of 2026-07-08

Supersedes the earlier "in progress" state of this SOP (image built, weights
transferring, container not yet started). The perception stage is now built,
running, tunneled, and reachable from a local orchestrator run.

## Why: Blackwell GPUs need a newer CUDA/torch base

`perception/Dockerfile`'s base image is parametrized via `ARG BASE_IMAGE`
(default `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`). That default
predates Blackwell (sm_120) and won't run on an RTX PRO 6000 / RTX 50-series
GPU. Build with the override:

```bash
docker build --build-arg BASE_IMAGE=pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel \
  -t wbk-perception:blackwell perception/
```

`requirements.txt` deliberately excludes `torch`/`torchvision` so the base
image's own torch build is used untouched. Verified on the server: `torch
2.8.0+cu128`, `transformers 4.57.1`, `ultralytics 8.4.90` all import cleanly.
(This is a separate torch build from the **training** venv's system torch,
`2.12.1+cu132` — see [System: Training](../System/training.md); the two
stacks are not required to match.)

## Weights: rsync instead of re-downloading, plus a trained YOLO mount

The GPU server has no HuggingFace auth configured, and SAM 3's weights
(`facebook/sam3`) are gated — re-authenticating on a headless server is extra
friction, and LocateAnything-3B is multi-GB. Instead, `rsync` the
already-downloaded model dirs from a local machine's HF cache into a
server-side cache directory, then mount that directory at the container's
`HF_HOME`:

```bash
rsync -a ~/.cache/huggingface/hub/models--facebook--sam3 \
        ~/.cache/huggingface/hub/models--nvidia--LocateAnything-3B \
        gpu-server:hf-cache/hub/
```

YOLO needs no such step for its stock weights — `ultralytics` auto-downloads
them on first load. But this project deploys a **custom-trained** YOLO
(`parts_detmask.pt`, 18 part classes, see [System: Training](../System/training.md))
instead of the stock default — that's a separate mount, covered below.

## Running containers on the server (bound to localhost only)

Two containers run on the GPU server, **not** the single-container-via-supervisord
layout `docker-compose.yml` describes for local/single-host use (see ADR 0001
for why perception is normally one shared container):

| Container | Serves | Ports (bound `127.0.0.1`) | GPU |
|---|---|---|---|
| `wbk-perception` | `yolo` (`:8001`→`6767`), `locateanything` (`:8003`→`6769`) | `6767`, `6769` | `device=1` |
| `wbk-sam3` | `sam3` (`:8002`→`6768`) | `6768` | (separate) |

`wbk-perception` still runs all three services under `supervisord`
(`perception/supervisord.conf`, unchanged from the single-container design),
but the `sam3` process **inside it fails to load** on this server — a
deployment-specific quirk, not yet root-caused this session. Real SAM3
traffic is served instead by the standalone `wbk-sam3` container on `:8002`
(`6768` on the server). Do not assume `wbk-perception`'s bundled `sam3`
process is usable; route SAM3 calls at `6768`/tunnel `18002` regardless of
which container "owns" port 8002 in the compose file.

Base container image: `wbk-perception:blackwell` (see build command above).
Recreating `wbk-perception` with new weights uses `docker run` directly (see
[System: Training](../System/training.md) "Deployment: `deploy_yolo_weights.sh`"),
not `docker compose` — the server-side deployment is hand-run, not
compose-managed.

Notes:
- Ports are bound to `127.0.0.1` on the server, never exposed on its public
  interface — the SSH tunnel below is the only intended ingress path.
- `WBK_API_TOKEN` (see [ADR 0009](../Decisions/0009-shared-token-auth.md))
  still applies here.

## Reaching it from the orchestrator: SSH port-forward tunnel

The current split (per root `README.md`'s topology table): **orchestrator +
damage + dashboard run on a local machine**; **perception + pose (+ YOLO
training) run on the GPU server**; a separate on-prem box runs the Isaac Sim
backend; the Jetson runs `robot_control`/`scene_camera` — the latter two are
outside this SOP's scope.

A `Host gpu-server` block in `~/.ssh/config` carries the forwards. Open the
tunnel from the local machine:

```bash
ssh -N gpu-server
# forwards: 18001->6767(yolo)  18002->6768(sam3)  18003->6769(locate)
#           18004->8004(fpose) 18005->8005(gigapose) 6006->6772(tensorboard)
```

Then bring up the local stack pointed at the tunnels — **not** the plain
`docker-compose.yml`, but with the remote-GPU override layered on top:

```bash
docker compose -f docker-compose.yml -f docker-compose.remote-gpu.yml \
  up -d orchestrator dashboard damage
```

`docker-compose.remote-gpu.yml` sets `PERCEPTION_YOLO_URL=http://localhost:18001`,
`PERCEPTION_SAM3_URL=http://localhost:18002`, `PERCEPTION_LOCATE_URL=http://localhost:18003`,
`POSE_URL=http://localhost:18004` (and other non-perception env, e.g. the
Isaac-Sim movement URL — out of scope here), and runs the `orchestrator`
service with `network_mode: host` so `localhost:1800x` reaches the tunnels
directly. **Do not** also start the local `perception`/`pose` services from
the base compose file — the tunnels replace them.

This is why the server binds every port to `127.0.0.1` instead of `0.0.0.0`:
the tunnel is the only intended ingress path. TensorBoard for training runs
(port `6772`→local `6006`) rides the same tunnel — see [System:
Training](../System/training.md).

## Deploying newly trained YOLO weights

Run on the server after a training run completes (`parts_detmask_v1` or
whichever run name):

```bash
ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_yolo_weights.sh'
```

This stages `runs/parts_detmask_v1/weights/best.pt` at
`/mnt/vss-data/kip/weights/parts_detmask.pt`, then recreates `wbk-perception`
(same image/ports/GPU as above) with
`-v /mnt/vss-data/kip/weights:/weights -e YOLO_WEIGHTS=/weights/parts_detmask.pt`,
and polls `GET :6767/health` for `loaded:true`. Verify further with
`YOLO(weights).names` — should list all 18 part classes — and by reloading
the dashboard and confirming detections against real parts. See [System:
Training](../System/training.md) for the full script breakdown and the
current model's mAP/recall numbers.

## Caveat: no isolation from co-tenants on a shared server

The GPU server is a single account / shared Docker daemon, not a dedicated or
sandboxed host, and is shared with other teams (see [System:
Training](../System/training.md) — pin to an idle GPU via `nvidia-smi`
before training). Anyone else with access to that account or daemon can read
container env vars (`docker inspect`, `/proc`), so **keep secrets off the
box** — notably the `OPENROUTER_API_KEY` (damage stage, not deployed here)
and, to a lesser extent, `WBK_API_TOKEN` (already documented as a
trusted-LAN-only control in [ADR 0009](../Decisions/0009-shared-token-auth.md),
not a real secret boundary).
