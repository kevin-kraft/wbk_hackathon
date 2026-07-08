# Deploying to the Jetson via native venv (not docker compose)

## Related Docs
- [System: Robot Control](../System/robot_control.md) — the `robot_control/` service this SOP deploys; see its "Deployment" section for the documented (currently non-working, on this device) compose path
- [ADR 0010: robot_control integration](../Decisions/0010-robot-control-integration.md) — why `robot_control/` is pinned to port `9000`, the shared-token auth pattern
- `robot_control/README.md`, `scene_camera/README.md` (in-repo) — each service's own endpoint docs
- `deploy/robot-control/docker-compose.yml` — the documented (currently unusable on the Jetson) deployment path this SOP works around

## Why not the documented `docker compose` path

`deploy/robot-control/docker-compose.yml` (pulling the published GHCR image,
`network_mode: host`) is the **intended** production path, but as of
2026-07-08 it does not work on the lab's Jetson (`lara5@172.22.192.166`, ssh
alias `jetson`), for two independent reasons:

1. **Image architecture mismatch.** `.github/workflows/publish-images.yml`'s
   `docker/build-push-action@v6` step has no `platforms:` key, so it builds
   for the runner's native arch only — **amd64**. The Jetson is **arm64**.
   The published `ghcr.io/kevin-kraft/wbk-robot-control` image cannot run
   there without a multi-arch rebuild.
2. **No docker access on the device.** The `lara5` user has neither
   docker-group membership nor passwordless `sudo`, so `docker compose` (or
   even plain `docker`) cannot run at all under that account, independent of
   the image-arch problem.

Neither is a code bug — both are infra gaps. See "To make the compose path
viable" below for what would actually close them.

Given that, `robot_control` and `scene_camera` were deployed the night of
2026-07-08 via a **native Python venv**, run directly under the `lara5`
account with `nohup`. This SOP documents that working path so it can be
repeated (or superseded once the compose path is fixed).

## Prerequisites

- SSH access: `ssh jetson` (alias for `lara5@172.22.192.166`).
- The Jetson has system Python 3.10 (works fine — nothing in
  `robot_control/` or `scene_camera/` requires 3.11-only syntax).
- The Jetson has a system-wide Zivid SDK 2.17.1 install with its Python
  bindings already on the system `site-packages` (needed for
  `scene_camera` — see below). This SOP does not install the Zivid SDK
  itself; it assumes it is already present, which it was on this device.
- The repo is **public** on GitHub — deploys are a fresh `git clone`, never
  an rsync of a local working tree. Only committed code reaches the device.

## Procedure

### 1. Clone (or update) the repo on the device

```bash
ssh jetson
git clone --depth 1 https://github.com/kevin-kraft/wbk_hackathon.git ~/wbk_hackathon
```

To update an existing checkout instead of re-cloning:

```bash
git -C ~/wbk_hackathon pull --ff-only
```

### 2. `robot_control` — plain venv

```bash
cd ~/wbk_hackathon/robot_control
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9000 >> ~/robot-control.log 2>&1 &
```

Verify:
```bash
curl localhost:9000/health          # {"status": "ok"}
curl localhost:9000/robot/probe     # safe, read-only — no motion
```

### 3. `scene_camera` — venv MUST use `--system-site-packages`

The Zivid SDK's Python bindings (and its `nptyping` dependency chain) are
only installed system-wide on this Jetson, not as a pip package — the venv
**must** inherit system packages or the Zivid import will fail:

```bash
cd ~/wbk_hackathon/scene_camera
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install "numpy<2" "opencv-python-headless<5"
```

The version pins matter and are **not** just "use latest":
- The system-wide zivid/nptyping stack requires **numpy 1.x** — numpy 2 breaks it.
- `opencv-python-headless>=5` requires numpy≥2 — directly conflicting with the pin above.
- The working combination verified on this device: **opencv 4.11 + numpy 1.26.4**.

Start it with `python -m uvicorn`, not the `uvicorn` binary directly —
a `--system-site-packages` venv does **not** create its own `uvicorn`
console-script entry point (it resolves the system one, if present, which
may be missing or the wrong version), so invoke it as a module instead:

```bash
nohup .venv/bin/python -m uvicorn scene_camera.app:app --host 0.0.0.0 --port 9002 >> ~/scene-camera.log 2>&1 &
```

Verify:
```bash
curl localhost:9002/health   # backend: "zivid", ready: true
curl -X POST localhost:9002/capture   # real frame, ~1s, 1224x1024, K from SDK
```

The camera itself is GigE, reachable at `192.168.2.31` over the Jetson's
`enP8p1s0` interface — this is a fixed hardware fact of the current bench
setup, not something this SOP configures.

### 4. Updating a running deployment

```bash
git -C ~/wbk_hackathon pull --ff-only

# robot_control
pgrep -f "uvicorn app.main" | xargs -r kill
cd ~/wbk_hackathon/robot_control
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9000 >> ~/robot-control.log 2>&1 &

# scene_camera
pgrep -f "python -m uvicorn scene_camera.app" | xargs -r kill
cd ~/wbk_hackathon/scene_camera
nohup .venv/bin/python -m uvicorn scene_camera.app:app --host 0.0.0.0 --port 9002 >> ~/scene-camera.log 2>&1 &
```

## Known limitations of this deployment

- **No process supervision.** `nohup` only — either process dies on crash
  or Jetson reboot and does not come back on its own. `lara5` has no sudo,
  so there's no systemd unit and no `loginctl enable-linger` for a user
  service either. If this needs to survive a reboot, that gap has to be
  closed first (see below).
- **The robot itself was not reachable at deploy time.** The LARA5 socket
  server (`127.0.0.1:65432`, what `robot_control` bridges to) was **not
  running** on the Jetson during this deployment — `GET /robot/probe`
  returned `Errno 111` (connection refused) until the robot team starts
  their side. `robot_control`'s own `/health` is independent of this and
  was green throughout.
- **Auth is off.** `WBK_API_TOKEN` is currently unset on both services, so
  the shared-token gate (ADR 0009) is disabled — anyone on the LAN can hit
  every endpoint. Fine for now on a trusted bench network; revisit before
  any less-trusted network exposure.
- **Shared device.** `lara5` is a shared account — keep all changes
  additive and scoped to its home directory (`~/wbk_hackathon`, the two
  `.log` files). Don't touch other users' processes or system-wide state.

## To make the documented `docker compose` path viable here

Two independent infra changes, neither done yet:
1. Add `platforms: linux/amd64,linux/arm64` to the `docker/build-push-action@v6`
   step in `.github/workflows/publish-images.yml` so GHCR images include an
   arm64 variant.
2. Get `lara5` added to the `docker` group on the Jetson (requires someone
   with sudo on that box — not currently available to this deployment).

Until both land, this native-venv path is the only way to run these two
services on this device.
