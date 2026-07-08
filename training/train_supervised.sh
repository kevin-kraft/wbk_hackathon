#!/usr/bin/env bash
# Crash-resilient training launcher. Runs train.py; if it exits non-zero
# (CUDA hiccup, OOM, SSH drop killing the process, ...), waits briefly and
# relaunches with --resume, which continues from weights/last.pt. Caps retries
# so a deterministic config error can't loop forever.
#
# Usage (wrap in screen so it survives logout):
#   screen -S det
#   bash /mnt/vss-data/kip/code/train_supervised.sh \
#       --data /mnt/vss-data/kip/datasets/parts_det/data.yaml \
#       --model yolo26m.pt --name parts_det_v1 --device 0 \
#       --epochs 120 --imgsz 1536 --batch 16
#   # Ctrl-A D to detach
#
# All args after this script are passed straight to train.py. On a crash the
# same args are reused with --resume appended.
set -uo pipefail
# shellcheck disable=SC1091
source /mnt/vss-data/kip/code/env.sh
cd /mnt/vss-data/kip/code

MAX_RETRIES="${MAX_RETRIES:-20}"
RETRY_SLEEP="${RETRY_SLEEP:-15}"

attempt=0
resume_flag=""
while :; do
    attempt=$((attempt + 1))
    echo "[supervisor] attempt $attempt/$((MAX_RETRIES + 1)) $(date -u +%FT%TZ) ${resume_flag}"
    # resume flag FIRST — train.py's --extra uses argparse.REMAINDER and must stay last
    # shellcheck disable=SC2068
    python train.py $resume_flag "$@"
    code=$?
    if [ $code -eq 0 ]; then
        echo "[supervisor] training finished cleanly (exit 0)"
        break
    fi
    if [ $attempt -gt "$MAX_RETRIES" ]; then
        echo "[supervisor] giving up after $attempt attempts (last exit $code)"
        exit $code
    fi
    echo "[supervisor] crash (exit $code) — resuming in ${RETRY_SLEEP}s"
    sleep "$RETRY_SLEEP"
    resume_flag="--resume"
done
