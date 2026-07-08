#!/usr/bin/env bash
# Deploy the trained YOLOv26 segmentation model (parts_seg_v1) as a sidecar
# perception service on the gpu-server. The prebuilt wbk-perception:blackwell
# image predates the `yoloseg` service, so instead of rebuilding we run a second
# container from that image with the updated perception source mounted over
# /app/perception (deps already baked in) and the seg weights bind-mounted.
#
# Prereq: the updated perception/ source must already be on the box at
#   /mnt/vss-data/kip/perception   (rsync'd from the laptop — see deploy note).
#
# Run ON the gpu-server:
#   ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_yolo_seg.sh'
set -euo pipefail

CODE=/mnt/vss-data/kip/perception                                  # updated perception source
SRC=/mnt/vss-data/kip/runs/parts_seg_v1/weights/best.pt
DST=/mnt/vss-data/kip/weights/parts_seg.pt
GPU_DEVICE=1            # co-locate with the detector (our GPU); plenty of headroom
HOST_PORT=6770         # -> local 18007 via the `ssh gpu-server` LocalForward

echo "=== 1. sanity: updated code present (yoloseg service) ==="
test -f "$CODE/services/yoloseg/main.py" || {
  echo "ERROR: $CODE/services/yoloseg/main.py missing."
  echo "       rsync the perception dir first, e.g. from the laptop:"
  echo "       rsync -a --delete perception/ gpu-server:$CODE/"
  exit 1
}

echo "=== 2. stage seg weights ==="
cp "$SRC" "$DST"
ls -la "$DST"

echo "=== 3. (re)create wbk-yoloseg sidecar ==="
docker rm -f wbk-yoloseg >/dev/null 2>&1 || true
docker run -d --name wbk-yoloseg \
  --gpus "\"device=${GPU_DEVICE}\"" \
  -p 127.0.0.1:${HOST_PORT}:8007 \
  -e PERCEPTION_DEVICE=cuda \
  -e WEIGHTS_DIR=/weights \
  -e YOLO_SEG_WEIGHTS=/weights/parts_seg.pt \
  -e YOLO_CONFIG_DIR=/tmp/ultralytics \
  -v /mnt/vss-data/kip/weights:/weights \
  -v "${CODE}":/app/perception \
  -w /app/perception \
  wbk-perception:blackwell \
  uvicorn services.yoloseg.main:app --host 0.0.0.0 --port 8007 >/dev/null

echo "=== 4. status ==="
sleep 3
docker ps --filter name=wbk-yoloseg --format "{{.Names}}  {{.Status}}  {{.Ports}}"

echo "=== 5. wait for model load, then health-check ==="
for i in $(seq 1 30); do
  out=$(curl -s --max-time 5 http://127.0.0.1:${HOST_PORT}/health 2>/dev/null || true)
  if [ -n "$out" ]; then echo "yoloseg /health: $out"; break; fi
  sleep 3
done
echo "done. Local access after 'ssh gpu-server': http://127.0.0.1:18007/health"
