# SOP: Deploying the pose services (podman, GPU server)

## Related Docs
- [System: Architecture](../System/architecture.md) — Stage 2 6DoF Pose, the `pipeline` options table
- [System: Integration Points](../System/integration_points.md) — Contract 2 (`POST /pose`), the `pipeline='2d'` addition
- [ADR 0016: GigaPose 2D (planar) pose mode](../Decisions/0016-gigapose-2d-planar-pose-mode.md) — why this mode exists and the graceful-degrade design
- [ADR 0009: shared-token auth](../Decisions/0009-shared-token-auth.md) — the `WBK_API_TOKEN` mechanism; this SOP notes pose sets it **required**, unlike perception
- [SOP: deploying perception to the GPU server](./deploy_perception_gpu_server.md) — the **docker**-based sibling deployment on the same GPU server; read that one first for the shared-server context (tunnel host, co-tenant caveat) — this SOP only covers what differs for pose
- [SOP: running the services](./running_services.md) — the local/single-host `docker compose up foundationpose gigapose` path this SOP is the deployed alternative to

## Status: deployed and running (2026-07-08)

`wbk-gigapose` and `wbk-foundationpose` run on the same shared GPU server as
perception (see [SOP: deploying perception to the GPU
server](./deploy_perception_gpu_server.md)), but on **podman, not docker** —
this is the single biggest gotcha for this SOP. `docker ps` will show
nothing for these two services; they are invisible to any docker tooling.

## Why podman here and docker for perception

Not a project decision — an inherited constraint of the shared GPU server's
environment for the pose model repos (FoundationPose/GigaPose upstream
tooling on this host was already set up against podman before this project
arrived). Perception's `wbk-perception`/`wbk-sam3`/`wbk-yoloseg` containers
are plain `docker`. Don't assume one container tool for "the GPU server" —
check which stage you're touching.

## Topology

| Container | Serves | Host port (bound `127.0.0.1`) | Local tunnel |
|---|---|---|---|
| `wbk-gigapose` | `gigapose` (`:8005` in-container) | `8005` | `18005` |
| `wbk-foundationpose` | `foundationpose` (`:8004` in-container) | `8004` | `18004` |

Both containers are **root-managed** under a custom podman store, not the
default rootless user store — every `podman` command against them needs the
explicit store flags:

```bash
sudo podman --root /mnt/vss-data/kip/podman/storage --runroot /run/containers/storage <cmd>
```

Forgetting the `--root`/`--runroot` flags (or `sudo`) will make `podman ps`
report neither container exists — it's looking at the wrong (default)
store, not evidence the containers are down.

The `wbk-gigapose` image (`localhost/wbk-gigapose-svc:latest`) bakes the
pose service code at `/svc` (`WORKDIR`/`PYTHONPATH=/svc`) at build time —
unlike perception's `wbk-yoloseg` sidecar pattern (ADR 0015), pose code is
**not** bind-mounted from a live source tree in general. Only the GigaPose
model repo itself is mounted (`/mnt/vss-data/kip/code/GigaPose ->
/workspace/GigaPose`, for the templates/meshes/adapter code GigaPose needs
at runtime) — the FastAPI service layer (`app.py`, `shared/`) lives inside
the image.

## Auth: `WBK_API_TOKEN` is REQUIRED on the pose services

Unlike perception (where `WBK_API_TOKEN` is currently **unset**, so
`require_token` is a no-op there — see [SOP: deploying perception to the
GPU server](./deploy_perception_gpu_server.md)), the deployed pose
containers run **with** `WBK_API_TOKEN` set. Every `POST /pose` call
(including through a local orchestrator over the tunnel) needs
`Authorization: Bearer <token>` or it 401s — see [ADR
0009](../Decisions/0009-shared-token-auth.md) for the mechanism.
`GET /health` stays open regardless (same as every other service). Do not
assume "pose" and "perception" share one auth posture just because they're
on the same server — verify per-service.

## No CAD templates deployed — `classes: []`, 6DoF is not currently usable

The running `wbk-gigapose` has no CAD meshes/templates registered for this
project's parts: `GET :8005/health`'s `classes` field returns `[]`, and any
`pipeline='rgb'`/`'rgbd'` request 503s ("6DoF model not loaded; use
pipeline='2d'"). This is the asset gap [ADR
0016](../Decisions/0016-gigapose-2d-planar-pose-mode.md) documents — it is
expected, not a broken deployment. **`pipeline='2d'` is the only working
pose path today** against this deployment. Producing and loading CAD
templates would change this; until then, don't route real-picking traffic
through `rgb`/`rgbd`.

## Deploying a pose-code change: `podman cp` + restart, not a rebuild

`training/deploy_gigapose_2d.sh` is the pattern used to ship the 2D mode
(and the template for future pose-code changes that don't touch the base
image's compiled CUDA extensions):

```bash
# 1. from the laptop/dev machine: stage the current pose/ tree
rsync -a --delete pose/ gpu-server:/mnt/vss-data/kip/pose/

# 2. on the server
ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_gigapose_2d.sh'
```

The script (`training/deploy_gigapose_2d.sh`):
1. Sanity-checks `$SRC/shared/planar.py` exists (fails fast with an rsync
   hint if the staged tree is stale/incomplete — same pattern as
   `deploy_yolo_seg.sh`'s sanity check, see
   [System: Training](../System/training.md)).
2. `podman cp`s the three changed files
   (`shared/planar.py`, `shared/schemas.py`, `gigapose_svc/app.py`) into
   `wbk-gigapose:/svc/...`, preserving their in-image relative paths.
3. `podman restart wbk-gigapose` — reuses the container's existing GPU
   device/mount/env configuration exactly as already configured; no
   `podman run` reconstruction, so there's no risk of dropping a flag from
   the original run command.
4. Polls `GET :8005/health` for up to ~2 minutes, printing the response —
   the graceful-degrade change (ADR 0016) means this poll succeeds even if
   the 6DoF model fails to load, since the service now starts regardless.

**Durability caveat**: `podman cp` writes into the container's writable
layer. This survives a `podman restart`/reboot of the container, but is
**lost on `podman rm`** (container deletion/recreation). For a durable fix
that survives container recreation, either rebuild the
`wbk-gigapose-svc` image from `/mnt/vss-data/kip/pose`, or recreate the
container with `-v /mnt/vss-data/kip/pose:/svc` (a bind mount, mirroring
perception's `wbk-yoloseg` sidecar pattern) instead of a baked-in `/svc`.
Neither has been done yet — the current deployment is a `cp`-patched image,
not a rebuilt or bind-mounted one. A teammate rebuilding/recreating either
pose container from scratch would lose this patch unless they redo the
`cp` step or fold `planar.py`/the schema/app changes into the image build.

## Reaching pose from a local orchestrator

Same SSH-tunnel convention as perception (see [SOP: deploying perception to
the GPU server](./deploy_perception_gpu_server.md) for the full `~/.ssh/config`
setup and the `docker-compose.remote-gpu.yml` bring-up command):

```bash
ssh -N gpu-server
# forwards include: 18004->8004 (foundationpose)  18005->8005 (gigapose)
```

`docker-compose.remote-gpu.yml` sets `POSE_URL=http://localhost:18004` —
the orchestrator's single `pose_url` config field (`orchestrator/config.py`)
defaults to **FoundationPose**, not GigaPose. `HttpPose.estimate()`
(`orchestrator/clients/http_pose.py`) also never sends a `pipeline` field at
all, so any request it makes falls back to `PoseRequest`'s own default,
`'rgbd'` — **the orchestrator does not yet call `pipeline='2d'` anywhere**.
Reaching the new 2D mode today means calling GigaPose directly (point at the
`18005` tunnel, set `"pipeline": "2d"` in the request body) rather than
through a live orchestrator run; there is no separate `GIGAPOSE_URL` env var
or pipeline-selection knob wired into the orchestrator client yet, only the
one `PoseClient` seam pointed at FoundationPose. Wiring the orchestrator to
use `pipeline='2d'` against GigaPose (given the no-CAD-templates reality
above, this is the only path that will currently return a real pose) is
follow-up work, not yet done. Add the bearer token to whatever client/`curl`
reaches either pose tunnel, per the auth section above — a plain
unauthenticated request that worked against perception's tunnel will 401
here.
