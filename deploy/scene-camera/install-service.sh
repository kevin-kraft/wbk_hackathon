#!/usr/bin/env bash
# Install + enable the scene_camera systemd service ON THE JETSON.
#
# Idempotent: safe to re-run after a `git pull`. It seeds the .env if missing,
# stops any manually-launched uvicorn holding :9002, installs/refreshes the unit,
# enables it (auto-start on boot) and starts it now, then verifies /health.
#
#   ssh jetson 'cd ~/wbk_hackathon && ./deploy/scene-camera/install-service.sh'
set -euo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
DIR="$REPO/deploy/scene-camera"
ENV_FILE="$DIR/.env"
UNIT_DST="/etc/systemd/system/scene-camera.service"

# Seed .env from the example on first install — remember to set WBK_API_TOKEN to
# match the orchestrator, else /capture auth won't line up.
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$DIR/.env.example" "$ENV_FILE"
  echo ">> Seeded $ENV_FILE from .env.example — set WBK_API_TOKEN to match the orchestrator."
fi

# Free :9002 from any hand-started instance before systemd takes it over.
pkill -f "uvicorn scene_camera.app:app" 2>/dev/null || true
sleep 1

sudo cp "$DIR/scene-camera.service" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable --now scene-camera.service

sleep 3
sudo systemctl --no-pager --full status scene-camera.service | head -n 12 || true
echo ">> /health:"
curl -s -m 8 http://127.0.0.1:9002/health && echo
