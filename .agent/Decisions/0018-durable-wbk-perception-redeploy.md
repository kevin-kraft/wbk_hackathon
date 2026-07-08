# ADR 0018: `wbk-perception` recreated durably — bind-mounted source, restart policy, trimmed to yolo+locateanything

## Related Docs
- [SOP: deploying perception to the GPU server](../SOP/deploy_perception_gpu_server.md) — the full updated container topology and the redeploy/update procedure this ADR's script implements
- [ADR 0001: perception shared container vs. pose split containers](./0001-perception-shared-container-pose-split-containers.md) — the original single-container-via-supervisord design this decision keeps for `wbk-perception` while trimming its program list
- [ADR 0015: YOLO-Seg sidecar container, no rebuild](./0015-yoloseg-sidecar-container-no-rebuild.md) — the `wbk-yoloseg` sidecar that (along with the standalone `wbk-sam3`) is why `wbk-perception` no longer needs to run `sam3`/`yoloseg` itself
- `deploy/perception/README.md`, `deploy/perception/redeploy-wbk-perception.sh` (in-repo) — the script and its own inline rationale this ADR documents

## Status
Accepted (2026-07-08, commit `7f12f41`).

## Context

The running `wbk-perception` container on the GPU server predated this
session's fixes and had two structural problems, discovered while debugging
the live rig:

1. **Baked-in code, hot-fixed via `docker cp`.** The `locateanything`
   `use_cache=True` fix (see [System: Integration
   Points](../System/integration_points.md) for the bug) was delivered by
   `docker cp`-ing the patched file straight into the running container —
   fast to apply, but **ephemeral**: lost on any container recreate, and
   unrecoverable after a `docker rm`/crash/host reboot with no trace it ever
   happened.
2. **`--restart no` (the default).** Nothing brings `wbk-perception` back up
   after a GPU-server reboot — `yolo` and `locateanything` would simply be
   down until someone noticed and manually re-ran the original `docker run`.
3. **A shadow `sam3` process wasting GPU memory.** `wbk-perception`'s baked
   `supervisord.conf` (the same one `docker-compose.yml`'s local single-host
   deployment uses, see ADR 0001) still tries to start `sam3` alongside
   `yolo`/`locateanything`, even though real `sam3` traffic is already served
   by the standalone `wbk-sam3` container (a pre-existing workaround for a
   different bug — `sam3` fails to load inside `wbk-perception` at all on
   this server, see ADR 0001's "Update" note). That failed/unused `sam3`
   process still occupied GPU memory on the same device as the working
   services.
4. **No way to restart one program without bouncing the whole container.**
   The baked config had no `supervisorctl` control socket configured, so the
   only way to reload a single failing/updated service was to `pkill` the
   process inside the container and hope `autorestart=true` picked it back
   up correctly, or recreate the whole container (losing (1) and dropping
   `locateanything`'s slow ~1-minute VLM load for both services, not just
   the one that changed).

## Decision

`deploy/perception/redeploy-wbk-perception.sh` durably recreates
`wbk-perception` on the GPU server:

- **Canonical source is bind-mounted**, not baked: `/mnt/vss-data/kip/perception`
  (rsync target, the same canonical path `wbk-yoloseg` already uses per
  [ADR 0015](./0015-yoloseg-sidecar-container-no-rebuild.md)) is mounted at
  `/app/perception`. Future code updates are edit-and-restart, not
  rebuild-and-recreate. The script sanity-checks the canonical source
  actually carries the `use_cache=True` and CORS fixes before proceeding, so
  it fails fast with a clear rsync hint rather than silently deploying a
  stale tree.
- **`--restart unless-stopped`** — survives a GPU-server reboot without
  manual intervention.
- **A dedicated `supervisord.wbk-perception.conf`** (written by the script
  onto the canonical source path) runs **only** `yolo` (`:8001`) and
  `locateanything` (`:8003`) — the two services this container actually
  publishes. No `sam3`, no `yoloseg`; those have their own containers
  (`wbk-sam3`, `wbk-yoloseg`) already.
- **A `supervisorctl` control socket** (`unix_http_server` +
  `[supervisorctl]` block pointing at `/tmp/supervisor.sock`) so a future
  code change to just `locateanything` (or just `yolo`) can be applied with
  `docker exec wbk-perception supervisorctl -c
  /app/perception/supervisord.wbk-perception.conf restart locateanything` —
  no full container recreate, no bouncing the sibling service, no repeating
  the ~1-minute LocateAnything-3B reload for a `yolo`-only change.

Idempotent — safe to re-run; it always `docker rm -f`s and recreates the
container from the same known image/ports/GPU/env, so a repeat run converges
to the same state rather than accumulating drift.

## Why

- **Ephemeral hotfixes are a standing risk, not a one-time inconvenience.**
  Every `docker cp` hotfix applied to this container was silently reverted
  the next time anyone recreated it for an unrelated reason (e.g. deploying
  new YOLO weights per the existing `deploy_yolo_weights.sh` path) — a
  guaranteed regression waiting to happen, not a hypothetical one, since a
  weights redeploy is a routine, expected operation on this project. A
  bind-mounted source makes fixes durable by construction: they live in the
  canonical `/mnt/vss-data/kip/perception` tree, the same place the
  `redeploy-wbk-perception.sh`/`deploy_yolo_seg.sh`/`deploy_yolo_weights.sh`
  scripts already sync to.
- **A shared GPU server has real memory pressure.** The server is shared
  with other teams (see [SOP: deploying perception to the GPU
  server](../SOP/deploy_perception_gpu_server.md) "Caveat: no isolation from
  co-tenants"); loading a `sam3` model that is both broken and already
  served elsewhere is pure waste on a resource other teams are also
  competing for.
- **Restart granularity matters when one service (LocateAnything-3B) is slow
  to load.** Without the control socket, any single-service fix cost a full
  container bounce — reloading both `yolo` (fast) and `locateanything`
  (~1 minute) even when only one of them changed. The socket makes the cost
  proportional to what actually changed.
- **This mirrors, rather than diverges from, the established pattern.** The
  bind-mounted-canonical-source shape is the same one [ADR
  0015](./0015-yoloseg-sidecar-container-no-rebuild.md) already established
  for `wbk-yoloseg` — applying it to `wbk-perception` too means the whole
  perception deployment on this server now follows one consistent update
  model instead of two (bake-and-rebuild for one container, mount-and-edit
  for another).

Rejected alternatives:
- **Rebuild `wbk-perception:blackwell` from current source and recreate.**
  Would also fix the ephemeral-hotfix problem, but re-triggers the full
  Blackwell `BASE_IMAGE` build-arg path (see [SOP: deploying perception to
  the GPU server](../SOP/deploy_perception_gpu_server.md)) for a change that
  doesn't touch any dependency — unnecessary build risk for a source-only
  fix, same reasoning ADR 0015 already used to reject a rebuild for
  `wbk-yoloseg`.
- **Leave `sam3` in the container's supervisord config** (just ignore its
  failure) — rejected once it was clear that process still reserves GPU
  memory on `device=1` even while crash-looping, with zero benefit since
  `wbk-sam3` already serves real `sam3` traffic.

## Consequences

- **`wbk-perception` now serves exactly `yolo` + `locateanything`** — down
  from three supervised programs (`yolo`, `sam3`, `locateanything`) to two.
  `sam3` traffic was already routed to `wbk-sam3` in practice (ADR 0001's
  "Update"), so this changes nothing about which endpoint answers `sam3`
  requests — it only stops wasting GPU memory on the broken in-container
  copy. `yoloseg` was never in this container's config (it's `wbk-yoloseg`,
  ADR 0015) and remains untouched.
  **Note: this container config also drops `sam3` entirely rather than
  leaving it crash-looping** — see [SOP: deploying perception to the GPU
  server](../SOP/deploy_perception_gpu_server.md) for the current three-
  container topology and whether that SOP's older "sam3 process inside
  wbk-perception fails to load" language still needs updating.
- **`wbk-perception`'s source is now the single canonical
  `/mnt/vss-data/kip/perception` tree**, same as `wbk-yoloseg`. Both
  containers mount the same host directory — a code change picked up by one
  is visible to the other immediately (though each still needs its own
  `supervisorctl restart <program>` / container restart to actually reload
  the running process).
- **Re-running the script bounces `yolo` + `locateanything`** (a fresh
  `docker run` recreate) — the script polls both `/health` endpoints for
  `loaded:true` afterward (up to 3 minutes, since the LocateAnything-3B load
  is slow) but this is not a zero-downtime operation. Run it in a quiet
  moment, per the script's own header comment.
- **Weights/HF-cache mounts are unchanged in shape** but now sit alongside
  the bind-mounted source in one `docker run` invocation instead of being
  set up once and left alone across ad-hoc `docker cp`s — see the script for
  the exact mount list (`/mnt/vss-data/kip/weights`, `/mnt/vss-data/kip/weights/hf-cache`).
