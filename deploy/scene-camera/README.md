# scene_camera (Zivid) deploy — on the Jetson

The Zivid **2+ L110** is a GigE camera (IP `192.168.2.30`); the capture service
serves `:9002` on the Jetson and is reached from the dashboard host over the
`ssh jetson` LocalForward (`127.0.0.1:9002`).

Two ways to run it. **Native + systemd is what we use** — the Jetson's system
`python3` already carries the Zivid SDK, and it's simpler than a privileged,
device-passthrough Docker container (see `docker-compose.yml` for the Docker path).

## Native + systemd (recommended, auto-starts on boot)

The unit runs `python3 -m uvicorn scene_camera.app:app --port 9002` from the repo
checkout at `/home/lara5/wbk_hackathon`, with `Restart=always` so it survives
crashes and reboots.

```bash
# On the Jetson, from the repo root:
git pull
./deploy/scene-camera/install-service.sh    # seeds .env, installs unit, enable --now, verifies /health
```

Ops:

```bash
sudo systemctl status  scene-camera     # state
sudo systemctl restart scene-camera     # bounce (e.g. after a git pull)
sudo systemctl stop    scene-camera     # take it down
journalctl -u scene-camera -f           # or: tail -f /home/lara5/scene-camera.log
```

`.env` (gitignored) is seeded from `.env.example` on first install — set
`WBK_API_TOKEN` to match the orchestrator, and `SCENE_CAMERA_BACKEND=zivid` for
the real camera (`mock`/`file` for hardware-free dev).

## Teardown

To stop auto-starting (e.g. dismantling the rig after the competition):

```bash
sudo systemctl disable --now scene-camera
sudo rm /etc/systemd/system/scene-camera.service && sudo systemctl daemon-reload
```
