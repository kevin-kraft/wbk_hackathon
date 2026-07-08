#!/usr/bin/env bash
# Deploy the trained YOLOv26 detection weights (parts_detmask_v1) to the
# wbk-perception container on the gpu-server. Recreates the container (same
# image/ports/gpu as the captured running config) with a /weights mount and
# YOLO_WEIGHTS pointing at our model. Run ON the gpu-server:
#   ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_yolo_weights.sh'
set -euo pipefail

SRC=/mnt/vss-data/kip/runs/parts_detmask_v1/weights/best.pt
DST=/mnt/vss-data/kip/weights/parts_detmask.pt

echo "=== 1. stage weights ==="
cp "$SRC" "$DST"
ls -la "$DST"

echo "=== 2. recreate wbk-perception (weights mount + YOLO_WEIGHTS) ==="
docker rm -f wbk-perception >/dev/null 2>&1 || true
docker run -d --name wbk-perception \
  --gpus '"device=1"' \
  -p 127.0.0.1:6767:8001 -p 127.0.0.1:6769:8003 \
  -e PERCEPTION_DEVICE=cuda \
  -e WEIGHTS_DIR=/weights \
  -e HF_HOME=/root/.cache/huggingface \
  -e YOLO_WEIGHTS=/weights/parts_detmask.pt \
  -v /mnt/vss-data/kip/weights:/weights \
  -v /mnt/vss-data/kip/weights/hf-cache:/root/.cache/huggingface \
  wbk-perception:blackwell \
  supervisord -c /app/perception/supervisord.conf >/dev/null

echo "=== 3. container status ==="
sleep 3
docker ps --filter name=wbk-perception --format "{{.Names}}  {{.Status}}  {{.Ports}}"

echo "=== 4. wait for yolo to load our model, then health-check ==="
for i in $(seq 1 20); do
  out=$(curl -s --max-time 5 http://127.0.0.1:6767/health 2>/dev/null || true)
  if [ -n "$out" ]; then echo "yolo /health: $out"; break; fi
  sleep 3
done
echo "locate /health: $(curl -s --max-time 5 http://127.0.0.1:6769/health 2>/dev/null || echo unreachable)"
