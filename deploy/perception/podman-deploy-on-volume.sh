#!/usr/bin/env bash
# Recover wbk-perception OFF the corrupted Docker store by running it under
# rootful PODMAN with storage on the healthy /mnt/vss-data volume — the same
# pattern the pose services (foundationpose/gigapose) already use. This bypasses
# both the corrupted Docker containerd store AND the 99%-full root disk, and
# touches no other team's containers.
#
# Serves yolo (:8001 -> host 6767) + locateanything (:8003 -> host 6769), the
# same host ports the SSH tunnels (18001/18003) already map. yolo loads the real
# LARA5 detector already staged at /weights/parts_detmask.pt.
#
# RUN ON gpu-server:
#   scp deploy/perception/podman-deploy-on-volume.sh gpu-server:/tmp/
#   ssh gpu-server 'bash /tmp/podman-deploy-on-volume.sh'
set -euo pipefail

VROOT=/mnt/vss-data/kip/podman/storage
CODE=/mnt/vss-data/kip/perception
BASE=docker.io/pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel
IMG=localhost/wbk-perception:blackwell
GPU=1
P=(sudo podman --root "$VROOT")

echo "=== 0. free space on the volume ==="
df -h /mnt/vss-data | tail -1

echo "=== 1. pull the torch/cuda base into the podman volume store ==="
"${P[@]}" image exists "$BASE" && echo "  base already present" || "${P[@]}" pull "$BASE"

echo "=== 2. build wbk-perception on the volume ==="
"${P[@]}" build --build-arg BASE_IMAGE="$BASE" -t "$IMG" "$CODE"

echo "=== 3. (re)create the podman container, publishing the same host ports ==="
"${P[@]}" rm -f wbk-perception >/dev/null 2>&1 || true
"${P[@]}" run -d --name wbk-perception \
  --restart unless-stopped \
  --runtime /usr/bin/nvidia-container-runtime \
  -e NVIDIA_VISIBLE_DEVICES="$GPU" \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  -p 127.0.0.1:6767:8001 \
  -p 127.0.0.1:6769:8003 \
  -e PERCEPTION_DEVICE=cuda \
  -e WEIGHTS_DIR=/weights \
  -e HF_HOME=/root/.cache/huggingface \
  -e YOLO_WEIGHTS=/weights/parts_detmask.pt \
  -e PYTHONUNBUFFERED=1 \
  -e LC_CTYPE=C.UTF-8 \
  -v /mnt/vss-data/kip/weights:/weights \
  -v /mnt/vss-data/kip/weights/hf-cache:/root/.cache/huggingface \
  -v "$CODE":/app/perception \
  -w /app/perception \
  "$IMG" \
  supervisord -c /app/perception/supervisord.wbk-perception.conf

echo "=== 4. wait for health (yolo :6767 fast, locateanything :6769 slow VLM load) ==="
for port in 6767 6769; do
  ok=""
  for i in $(seq 1 90); do
    out=$(curl -s --max-time 5 "http://127.0.0.1:${port}/health" 2>/dev/null || true)
    if echo "$out" | grep -q '"loaded":true'; then ok="$out"; break; fi
    sleep 2
  done
  echo "  :${port} -> ${ok:-TIMED OUT (check: sudo podman --root $VROOT logs wbk-perception)}"
done

echo
echo "DONE. wbk-perception now runs under podman on /mnt/vss-data (off the bad disk)."
echo "yolo detection = host :6767 (local tunnel :18001), serving the real LARA5 model."
