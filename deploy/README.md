# Deploy — single-service, no repo clone

Deploy any one service to any machine with **just Docker + a pull + the one small
compose file in that service's folder here**. The target never clones the repo.

## Model

Images are published to the **GitHub Container Registry (GHCR)**, public:

```
ghcr.io/kevin-kraft/wbk-orchestrator
ghcr.io/kevin-kraft/wbk-damage
ghcr.io/kevin-kraft/wbk-dashboard
```

Building + pushing is done by CI (`.github/workflows/publish-images.yml`, manual
`workflow_dispatch` or a `v*` tag) — you don't build on your laptop for a deploy.

## Deploy one service

Copy the single compose file (a few KB) to the target and bring it up:

```bash
scp deploy/damage/docker-compose.yml ubuntu@HOST:~/damage/
scp deploy/damage/.env.example       ubuntu@HOST:~/damage/.env   # fill in secrets
ssh ubuntu@HOST 'cd damage && docker compose pull && docker compose up -d'
```

Update later: re-run CI to push a new image, then on the target
`docker compose pull && docker compose up -d`. To stop: `docker compose down`.

Public images need no `docker login` to pull. (Private ones would need a PAT with
`read:packages`.)

## What's here vs. built on the server

| Service | Deploy artifact | Why |
|---|---|---|
| `orchestrator/` | GHCR image + this compose | CPU, small, self-contained |
| `damage/` | GHCR image + this compose | CPU, small; reference images baked in (see its README note) |
| `dashboard/` | GHCR image + this compose | static nginx; only `config.json` is copied alongside |
| **perception** | **built on the GPU server** | multi-GB CUDA image; runs only where the GPUs are |
| **pose** (foundationpose/gigapose) | **built on the GPU server** | ~32 GB each + needs the `*:blackwell` base images and the FoundationPose/GigaPose source trees |

For the GPU services, on the server: `git pull && docker compose build perception foundationpose gigapose && docker compose up -d <svc>` — no registry round-trip.

## First push: make the package public (one time)

After the first CI push, each GHCR package is **private by default**. In GitHub →
your profile/org → Packages → each `wbk-*` package → *Package settings* → change
visibility to **Public**. Then targets can pull with no auth.
