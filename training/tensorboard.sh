#!/usr/bin/env bash
# Launch TensorBoard on the shared GPU server, bound to a namespaced localhost
# port. Browse it locally at http://localhost:6006 (the `ssh gpu-server`
# LocalForward maps local 6006 -> server 127.0.0.1:6772).
#
#   ssh gpu-server            # keep this session open (carries the forward)
#   # in another shell:
#   ssh gpu-server 'bash /mnt/vss-data/kip/code/tensorboard.sh'
#
# Runs in the foreground; wrap in screen/nohup to persist. Reads all runs under
# /mnt/vss-data/kip/runs (Ultralytics writes TB event files there per run).
set -euo pipefail
# shellcheck disable=SC1091
source /mnt/vss-data/kip/code/env.sh

PORT="${TB_PORT:-6772}"
LOGDIR="${TB_LOGDIR:-/mnt/vss-data/kip/runs}"
mkdir -p "$LOGDIR"

echo "[tb] tensorboard --logdir $LOGDIR --host 127.0.0.1 --port $PORT"
echo "[tb] browse locally at http://localhost:6006  (via ssh gpu-server LocalForward)"
exec tensorboard --logdir "$LOGDIR" --host 127.0.0.1 --port "$PORT" --reload_interval 30
