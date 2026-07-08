# SOP: Deploying perception to the remote GPU server

## Related Docs
- [Architecture](../System/architecture.md) — Stage 1 Perception (`perception/`), the service/port map
- [Integration Points](../System/integration_points.md) — the HF weight cache mount, the `/infer` contract, shared-token auth
- [System: Training](../System/training.md) — where the deployed weights (`YOLO_WEIGHTS`/`YOLO_SEG_WEIGHTS`) come from
- [ADR 0015: YOLO-Seg sidecar container, no rebuild](../Decisions/0015-yoloseg-sidecar-container-no-rebuild.md) — why `wbk-yoloseg` is a third container instead of a `wbk-perception` rebuild
- [ADR 0018: durable `wbk-perception` redeploy](../Decisions/0018-durable-wbk-perception-redeploy.md) — why `wbk-perception` was recreated with bind-mounted source, a restart policy, and a trimmed (`yolo`+`locateanything`-only) supervisord config
- [ADR 0017: gray-world white balance + lowered detection confidence](../Decisions/0017-grayworld-white-balance-sim-to-real.md) — the sim-to-real fixes verified against this deployment
- [SOP: running the services](./running_services.md) — the local/single-host `docker compose up perception` path this SOP is an alternative to
- `deploy/README.md` (repo root) — the single-service GHCR deploy model for `orchestrator`/`damage`/`dashboard`; perception and pose are explicitly **not** part of that (built on the GPU server instead, see its table)
- `deploy/perception/README.md`, `deploy/perception/redeploy-wbk-perception.sh` (in-repo) — the durable-recreate script this SOP's "Redeploying `wbk-perception`" section covers, and its own condensed topology summary
- `perception/README.md` — "Newer GPUs (Blackwell / sm_120)" and "Deploying to a remote GPU server" sections; this SOP is the `.agent/`-side pointer to that content plus the wider topology
- Root [`README.md`](../../README.md) "Deployment" — the canonical, current 4-host topology table this SOP's perception slice is part of
- [System: Orchestrator](../System/orchestrator.md) "Robot target selection" / [ADR 0014](../Decisions/0014-robot-target-real-sim-both.md) — the `docker-compose.remote-gpu.yml` overlay this SOP describes also carries the Isaac Sim (`MOVEMENT_SIM_URL`) env for the same host; out of scope here, covered there

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

The `wbk-perception`/`wbk-yoloseg` `docker run` invocations (see
"Redeploying `wbk-perception`" below) mount the server-side cache from
`/mnt/vss-data/kip/weights/hf-cache` (not the bare `~/hf-cache/hub/` path
above, which is where the rsync lands before being organized under the
canonical `/mnt/vss-data/kip/weights` tree alongside the YOLO weights).

## Running containers on the server (bound to localhost only)

**Three** containers run on the GPU server, **not** the single-container-via-supervisord
layout `docker-compose.yml` describes for local/single-host use (see ADR 0001
for why perception is normally one shared container):

| Container | Serves | Ports (bound `127.0.0.1`) | GPU | Source |
|---|---|---|---|---|
| `wbk-perception` | `yolo` (`:8001`→`6767`), `locateanything` (`:8003`→`6769`) | `6767`, `6769` | `device=1` | bind-mounted `/mnt/vss-data/kip/perception` |
| `wbk-sam3` | `sam3` (`:8002`→`6768`) | `6768` | (separate) | (own image) |
| `wbk-yoloseg` | `yoloseg` (`:8007`→`6770`) | `6770` | `device=1` (co-located with `wbk-perception`) | bind-mounted `/mnt/vss-data/kip/perception` |

**Updated 2026-07-08 (commit `7f12f41`, [ADR 0018](../Decisions/0018-durable-wbk-perception-redeploy.md)):**
`wbk-perception` runs a **dedicated** `supervisord.wbk-perception.conf` —
generated by `deploy/perception/redeploy-wbk-perception.sh`, written onto the
canonical source tree — that starts **only** `yolo` and `locateanything`.
The stock `perception/supervisord.conf` (all four programs: `yolo`, `sam3`,
`yoloseg`, `locateanything`) is still what `docker-compose.yml`'s
local/single-host build uses, but `wbk-perception` on this server no longer
runs it — the container previously also tried to start `sam3` (which fails
to load on this server — a deployment-specific quirk, not yet root-caused)
and wasted GPU memory on the crash-looping process even though real SAM3
traffic was already served by the standalone `wbk-sam3` container. That
redundant `sam3` program is now dropped from `wbk-perception`'s config
entirely, not just failing silently. Real SAM3 traffic still comes from
`wbk-sam3` on `:8002` (`6768` on the server, tunnel `18002`) — route SAM3
calls there regardless of which container "owns" port 8002 in the compose
file.

`wbk-perception`'s canonical source-of-truth is now **bind-mounted**, the
same as `wbk-yoloseg`'s — `/mnt/vss-data/kip/perception` mounted at
`/app/perception`, not baked into the image. The container also runs with
`--restart unless-stopped` (was `--restart no`) and a `supervisorctl`
control socket, so a single program can be restarted without bouncing its
sibling or losing state across a host reboot. See "Redeploying
`wbk-perception`" below for the procedure and why this changed (ADR 0018 —
in short: a prior hotfix delivered via `docker cp` was silently lost on the
next unrelated container recreate).

`wbk-yoloseg` (added 2026-07-08) is a **third sidecar**, for a different
reason than `wbk-sam3`: it doesn't work around a broken in-image process, it
runs a service (`yoloseg`) that didn't exist yet when `wbk-perception:blackwell`
was built. Rather than rebuild that image, `wbk-yoloseg` runs from the
*same* image with the current `perception/` source bind-mounted over
`/app/perception` (so it picks up the `services/yoloseg/` code without the
image needing to contain it) and an overridden command
(`uvicorn services.yoloseg.main:app --port 8007` instead of `supervisord`),
so it serves *only* `yoloseg` — see
[ADR 0015](../Decisions/0015-yoloseg-sidecar-container-no-rebuild.md) for
the full rationale and consequences. (Its "`wbk-perception`'s own baked-in
source is now stale relative to the repo" consequence is now superseded —
`wbk-perception` bind-mounts the same canonical source as of ADR 0018.)

**Host-port gotcha, worth repeating:** the GPU server is shared with other
teams. Host port `8001` belongs to a **different team's** service, not this
project's `yolo`. This project's four perception ports on the host are
`6767` (`yolo`), `6768` (`sam3`), `6769` (`locateanything`), `6770`
(`yoloseg`) — the container-internal ports `8001`/`8002`/`8003`/`8007` never
appear on the host's port space. Don't `curl gpu-server:8001` expecting this
project's detector.

Base container image: `wbk-perception:blackwell` (see build command above).
Recreating `wbk-perception` — whether for new weights or a code fix — uses
`docker run` directly (see "Redeploying `wbk-perception`" below, and
[System: Training](../System/training.md) "Deployment: `deploy_yolo_weights.sh`"
for the weights-only path), not `docker compose` — the server-side
deployment is hand-run, not compose-managed. `wbk-yoloseg` is
deployed/redeployed the same hand-run way, via `training/deploy_yolo_seg.sh`
(see below).

Notes:
- Ports are bound to `127.0.0.1` on the server, never exposed on its public
  interface — the SSH tunnel below is the only intended ingress path.
- `WBK_API_TOKEN` (see [ADR 0009](../Decisions/0009-shared-token-auth.md))
  still applies here.

## Redeploying `wbk-perception` (durable recreate)

`deploy/perception/redeploy-wbk-perception.sh` (added 2026-07-08, commit
`7f12f41`, [ADR 0018](../Decisions/0018-durable-wbk-perception-redeploy.md))
recreates the container **durably** — bind-mounted canonical source,
`--restart unless-stopped`, the trimmed yolo+locateanything-only supervisord
config from the table above, and a `supervisorctl` control socket. Run it
whenever `wbk-perception` needs to be recreated for a reason other than a
routine weights deploy (that path is `deploy_yolo_weights.sh`, unchanged —
see [System: Training](../System/training.md)):

```bash
scp deploy/perception/redeploy-wbk-perception.sh gpu-server:/tmp/
ssh gpu-server 'bash /tmp/redeploy-wbk-perception.sh'
```

This bounces `yolo` + `locateanything` — the script polls both `/health`
endpoints for `loaded:true` afterward (up to 3 minutes, since the
LocateAnything-3B load is slow). Idempotent; safe to re-run. It sanity-checks
the canonical source (`/mnt/vss-data/kip/perception`) actually carries the
`use_cache=True` (locateanything) and CORS (`app_factory.py`) fixes before
proceeding — see [System: Integration Points](../System/integration_points.md)
for what those fixes are — and fails fast with an rsync hint if the source
hasn't been synced yet.

**Updating perception code afterwards needs no rebuild or recreate** — the
source is bind-mounted, so:

```bash
# edit /mnt/vss-data/kip/perception/... on the box (or rsync perception/ to
# it from the laptop), then restart just the changed program:
docker exec wbk-perception supervisorctl \
  -c /app/perception/supervisord.wbk-perception.conf restart locateanything   # or: yolo
```

See `deploy/perception/README.md` for the condensed version of this section
plus the teardown command (`docker rm -f wbk-perception wbk-sam3 wbk-yoloseg`).

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
# forwards: 18001->6767(yolo)  18002->6768(sam3)  18003->6769(locate)  18007->6770(yoloseg)
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
Isaac-Sim movement URL, `MOVEMENT_SIM_URL` — out of scope here, see
[System: Orchestrator](../System/orchestrator.md) "Robot target selection"
and [ADR 0014](../Decisions/0014-robot-target-real-sim-both.md)), and runs
the `orchestrator`
service with `network_mode: host` so `localhost:1800x` reaches the tunnels
directly. **Do not** also start the local `perception`/`pose` services from
the base compose file — the tunnels replace them.

This is why the server binds every port to `127.0.0.1` instead of `0.0.0.0`:
the tunnel is the only intended ingress path. TensorBoard for training runs
(port `6772`→local `6006`) rides the same tunnel — see [System:
Training](../System/training.md).

Note: `yoloseg` (tunnel `18007`) is **not** consumed by the orchestrator —
`docker-compose.remote-gpu.yml` has no `PERCEPTION_YOLOSEG_URL` because
`orchestrator/clients/`'s `PerceptionClient` never calls it. It's wired only
through the dashboard's own runtime config
(`frontend/public/config.json`/`deploy-local/config.json`'s `yoloseg` key,
see [System: Dashboard](../System/dashboard.md)) for manual inspection on
the Perception page. Bring up the tunnel regardless if you want that page's
YOLO-Seg option to work.

## Deploying the trained YOLO-Seg (instance segmentation) model

Run on the server after a `parts_seg_v1`-style training run completes (see
[System: Training](../System/training.md)):

```bash
# 1. from the laptop/dev machine: sync the *current* perception/ source —
#    the running wbk-perception:blackwell image predates the yoloseg service
#    dir, so the sidecar container needs it mounted, not baked in.
rsync -a --delete perception/ gpu-server:/mnt/vss-data/kip/perception/

# 2. on the server: stage weights + (re)create the wbk-yoloseg sidecar
ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_yolo_seg.sh'
```

This is a **new sidecar container** (`wbk-yoloseg`, `127.0.0.1:6770:8007`,
`--gpus device=1`, co-located with `wbk-perception`), not a
`wbk-perception` recreate — see [ADR
0015](../Decisions/0015-yoloseg-sidecar-container-no-rebuild.md) for why,
and [System: Training](../System/training.md) "Deployment:
`deploy_yolo_seg.sh`" for the full script breakdown (the source-sync sanity
check, the mount/env layout, the health-check poll) and the current
model's mAP/recall numbers. Verified end-to-end against a real dataset
frame: 8 masks at 0.96–0.99 confidence, valid full-res PNG masks (alongside
7 `parts_detmask` detection boxes at 0.99–1.0 from the same frame).

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
