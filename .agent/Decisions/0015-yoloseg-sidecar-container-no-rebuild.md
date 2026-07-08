# ADR 0015: YOLO-Seg deploys as a sidecar container with mounted source, not an image rebuild

## Related Docs
- [System: Architecture](../System/architecture.md) — Stage 1 Perception, the new `yoloseg` service
- [SOP: deploying perception to the GPU server](../SOP/deploy_perception_gpu_server.md) — the `wbk-yoloseg` container in the running topology
- [ADR 0001: perception shared container vs. pose split containers](./0001-perception-shared-container-pose-split-containers.md) — the earlier `wbk-sam3` sidecar workaround this decision extends
- [ADR 0012: mask-derived detection labels](./0012-mask-derived-detection-labels.md) — `parts_seg_v1`, the model this service serves

## Status
Accepted (2026-07-08, commit `27fee6c`).

## Context

`perception/services/yoloseg/` (a new FastAPI service serving the trained
`parts_seg_v1` YOLOv26-seg model) was added to the perception codebase after
`wbk-perception:blackwell` — the image already built and running on the
GPU server — was built. That image's `perception/` source tree, baked into
the image at build time, predates the `yoloseg` service directory entirely:
`services/yoloseg/main.py` does not exist inside the image.

Two ways to get `yoloseg` running on the server:

1. Rebuild `wbk-perception:blackwell` from the current `perception/` source
   and recreate the container.
2. Run a **second** container from the *existing* image, with the updated
   `perception/` source bind-mounted over `/app/perception`, serving only
   the new `services.yoloseg.main:app`.

## Decision

Went with (2): `training/deploy_yolo_seg.sh` runs a new sidecar container,
`wbk-yoloseg`, from the same `wbk-perception:blackwell` image already on the
server — no rebuild. It bind-mounts the updated `perception/` source
(rsync'd to `/mnt/vss-data/kip/perception` first) over `/app/perception` and
the `parts_seg_v1` weights over `/weights`, then overrides the container
command to `uvicorn services.yoloseg.main:app --host 0.0.0.0 --port 8007`
instead of the image's default `supervisord` entrypoint (so this container
runs *only* `yoloseg`, not a second copy of `yolo`/`sam3`/`locateanything`).
Pinned to `--gpus device=1`, the same GPU already used by the detector
(`wbk-perception`) — there was headroom, and it avoids touching whichever GPU
`wbk-sam3` (see ADR 0001's update) is on. Published on host port `6770`
(container `8007`), joining the existing `6767`/`6768`/`6769` map — reached
locally through the same `ssh gpu-server` tunnel, extended with a new
`18007→6770` forward.

This is the same shape as the pre-existing `wbk-sam3` sidecar (ADR 0001's
"Update" note) — a second container running one service off the shared base
image — for a different root cause (a service the base image predates,
rather than one that fails to load inside it).

## Why

- **The prebuilt image already works and is serving live traffic** (`yolo`,
  `sam3` via its sidecar, `locateanything`) on the shared GPU server. All
  three existing services depend on it; a rebuild-and-recreate risks an
  outage or a broken `wbk-perception` container mid-hackathon for the sake
  of adding one new endpoint.
- **All the dependencies `yoloseg` needs (`ultralytics`, torch, the shared
  `perception/services/shared/` code) are already baked into the image.**
  Only the Python source for the new service dir and its weights are
  missing — both are cheap to supply via a bind mount, without touching the
  installed package set.
- **A rebuild would also require re-verifying the Blackwell `BASE_IMAGE`
  build-arg override** (`pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel`, see
  [SOP: deploying perception to the GPU server](../SOP/deploy_perception_gpu_server.md))
  end to end again — extra risk for no benefit when the running image is
  already known-good.
- Source-mount sidecars are now this project's established pattern for
  "new code, unchanged base image" on this server (mirrors the `wbk-sam3`
  workaround), so a teammate encountering a third such case has precedent
  to follow rather than inventing a new deployment shape.

## Consequences

- `wbk-perception:blackwell` is now effectively **stale relative to the
  in-repo `perception/` source** — its baked-in copy lacks the `yoloseg`
  service dir. The other three services (`yolo`, `sam3` inside the shared
  image, `locateanything`) still run off the image's original baked-in code,
  not the mounted source, since only `wbk-yoloseg` mounts it. A future image
  rebuild would need to reconcile this (or the mount pattern could be
  extended to `wbk-perception` itself, at the cost of losing the "baked,
  reproducible image" property for local/single-host deployments).
- **Three** containers now run perception on the GPU server:
  `wbk-perception` (`yolo`, `locateanything`, plus a `sam3` process that
  fails to load), `wbk-sam3` (serves `sam3` for real), and `wbk-yoloseg`
  (serves `yoloseg`) — see [SOP: deploying perception to the GPU
  server](../SOP/deploy_perception_gpu_server.md) for the full topology
  table. The local/single-host `docker-compose.yml` path is unaffected —
  there, `yoloseg` runs as a fourth `supervisord` program inside the single
  `perception` container, since the local image is always built fresh from
  current source.
- The updated `perception/` source must be rsync'd to
  `/mnt/vss-data/kip/perception` on the server *before* running
  `deploy_yolo_seg.sh` — the script sanity-checks for
  `$CODE/services/yoloseg/main.py` and fails fast with an rsync hint if it's
  missing, rather than silently mounting a stale/partial tree.
- **New host-port gotcha, worth stating explicitly:** the GPU server is
  shared with other teams. Host port `8001` is a *different team's* service,
  not this project's `yolo`. This project's perception ports on the host are
  `6767` (`yolo`/detection), `6768` (`sam3`), `6769` (`locateanything`),
  `6770` (`yoloseg`) — container-internal ports `8001`/`8002`/`8003`/`8007`
  never appear on the host's public port space. SSH tunnels map
  local `18001→6767`, `18002→6768`, `18003→6769`, `18007→6770`. Do not port
  a `curl gpu-server:8001` habit from local dev to this server — it will
  either fail or, worse, hit someone else's service.
