# SOP: Deploying perception to a remote GPU server

## Related Docs
- [Architecture](../System/architecture.md) — Stage 1 Perception (`perception/`), the service/port map
- [Integration Points](../System/integration_points.md) — the HF weight cache mount, the `/infer` contract, shared-token auth
- [SOP: running the services](./running_services.md) — the local/single-host `docker compose up perception` path this SOP is an alternative to
- `deploy/README.md` (repo root) — the single-service GHCR deploy model for `orchestrator`/`damage`/`dashboard`; perception and pose are explicitly **not** part of that (built on the GPU server instead, see its table)
- `perception/README.md` — "Newer GPUs (Blackwell / sm_120)" and "Deploying to a remote GPU server" sections; this SOP is the .agent/-side pointer to that content plus the wider topology

## Status: in progress, as of 2026-07-07

This is **not yet a working deployment**. Current state:
- The perception image has been built on the GPU server with the Blackwell
  base image (commit `5fbacdf`) and verified to import (`torch 2.8.0+cu128`,
  `transformers 4.57.1`, `ultralytics 8.4.90`).
- Model weights are **transferring** (rsync) from a local machine into the
  server's HF cache.
- The container is **not yet running** on the server, and the **SSH tunnel is
  not yet established**.
- **Pose** (foundationpose/gigapose) deployment to the same server has not
  started — this SOP covers perception only.

Do not assume `PERCEPTION_*_URL` is reachable from a live orchestrator run
against this server yet.

## Why: Blackwell GPUs need a newer CUDA/torch base

`perception/Dockerfile`'s base image is parametrized via `ARG BASE_IMAGE`
(default `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`, commit `5fbacdf`).
That default predates Blackwell (sm_120) and won't run on an RTX PRO 6000 /
RTX 50-series GPU. Override it at build time:

```bash
docker build --build-arg BASE_IMAGE=pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel \
  -t wbk-perception:blackwell perception/
```

`requirements.txt` deliberately excludes `torch`/`torchvision` (see its header
comment) so the base image's own torch build is used untouched — this is what
makes the override work without a dependency fight. Verified on the server:
`torch 2.8.0+cu128`, `transformers 4.57.1`, `ultralytics 8.4.90` all import
cleanly.

## Weights: rsync instead of re-downloading

The GPU server has no HuggingFace auth configured, and SAM 3's weights
(`facebook/sam3`) are gated — re-authenticating on a headless server is extra
friction, and LocateAnything-3B is multi-GB. Instead, `rsync` the already-
downloaded model dirs from a local machine's HF cache into a server-side
cache directory, then mount that directory at the container's `HF_HOME`:

```bash
rsync -a ~/.cache/huggingface/hub/models--facebook--sam3 \
        ~/.cache/huggingface/hub/models--nvidia--LocateAnything-3B \
        <server>:hf-cache/hub/
```

YOLO needs no such step — `ultralytics` auto-downloads its (small, ungated)
weights on first load.

## Running the container (server-side, bound to localhost only)

```bash
docker run -d --gpus '"device=1"' \
  -p 127.0.0.1:6767:8001 -p 127.0.0.1:6768:8002 -p 127.0.0.1:6769:8003 \
  -v ~/hf-cache:/root/.cache/huggingface -e WBK_API_TOKEN=... wbk-perception:blackwell
```

Notes:
- Ports are bound to `127.0.0.1` on the server, **not** exposed on the
  server's public interface — the only intended path in is the SSH tunnel
  below.
- `WBK_API_TOKEN` (see [ADR 0009](../Decisions/0009-shared-token-auth.md))
  still applies here — set it and it gates `POST /infer` on all three
  services exactly as it does locally.
- The `--gpus '"device=1"'` pins a specific GPU on a multi-GPU box; adjust or
  drop for a single-GPU server.

## Reaching it from the orchestrator: SSH port-forward tunnel

The intended runtime split is: **orchestrator + damage + dashboard run on a
local machine**; **perception + pose run on the GPU server**. Rather than
exposing the server's ports publicly or reconfiguring the orchestrator's
`PERCEPTION_*_URL` to point at a remote host, the local machine opens an SSH
tunnel that remaps the server's `127.0.0.1:6767-6769` back onto its own
`localhost:8001-8003`:

```bash
ssh -L 8001:localhost:6767 -L 8002:localhost:6768 -L 8003:localhost:6769 <server>
```

With the tunnel up, the orchestrator's existing `PERCEPTION_YOLO_URL` /
`PERCEPTION_SAM3_URL` / `PERCEPTION_LOCATE_URL` env vars stay at their normal
`http://localhost:800{1,2,3}` defaults (see `orchestrator/config.py`,
`deploy/orchestrator/.env.example`) — no orchestrator-side config change is
needed, only the tunnel. This is why the server binds `127.0.0.1` instead of
`0.0.0.0`: the tunnel is the only intended ingress path.

Pose is expected to follow the same pattern once it's deployed to the server
(its own remapped local ports), but that has not happened yet.

## Caveat: no isolation from co-tenants on a shared server

The GPU server is a single account / shared Docker daemon, not a dedicated or
sandboxed host. Anyone else with access to that account or daemon can read
container env vars (`docker inspect`, `/proc`), so **keep secrets off the
box** — notably the `OPENROUTER_API_KEY` (damage stage, not deployed here)
and, to a lesser extent, `WBK_API_TOKEN` (already documented as a
trusted-LAN-only control in [ADR 0009](../Decisions/0009-shared-token-auth.md),
not a real secret boundary). This is the same shared-tenancy caveat as ADR
0009's threat model, just extended to a remote box instead of a local LAN.
