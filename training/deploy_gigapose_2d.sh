#!/usr/bin/env bash
# Deploy the gigapose 2D (planar) pose mode to the running wbk-gigapose podman
# container. The service code is baked at /svc in localhost/wbk-gigapose-svc,
# so we copy the updated (committed) files into /svc and restart — preserves the
# container's GPU/mount/env config exactly (no fragile podman-run reconstruction).
# The graceful-degrade change means the restart comes up even if the 6DoF model
# reload fails (2D is model-free).
#
# Prereq: pose/ rsync'd to /mnt/vss-data/kip/pose.
# Run ON the gpu-server:  ssh gpu-server 'bash /mnt/vss-data/kip/code/deploy_gigapose_2d.sh'
#
# NOTE: podman cp writes to the container's writable layer (durable across
# restart, lost on `podman rm`). For a durable deploy, rebuild the
# wbk-gigapose-svc image from /mnt/vss-data/kip/pose or recreate with
# -v /mnt/vss-data/kip/pose:/svc.
set -euo pipefail

SRC=/mnt/vss-data/kip/pose
PODMAN="sudo podman --root /mnt/vss-data/kip/podman/storage --runroot /run/containers/storage"

test -f "$SRC/shared/planar.py" || { echo "ERROR: $SRC/shared/planar.py missing — rsync pose/ first"; exit 1; }

echo "=== 1. copy updated pose code into wbk-gigapose:/svc ==="
$PODMAN cp "$SRC/shared/planar.py"    wbk-gigapose:/svc/shared/planar.py
$PODMAN cp "$SRC/shared/schemas.py"   wbk-gigapose:/svc/shared/schemas.py
$PODMAN cp "$SRC/gigapose_svc/app.py" wbk-gigapose:/svc/gigapose_svc/app.py

echo "=== 2. restart wbk-gigapose ==="
$PODMAN restart wbk-gigapose

echo "=== 3. health (waits for model load / 2D-only startup) ==="
for i in $(seq 1 40); do
  out=$(curl -s --max-time 5 http://127.0.0.1:8005/health 2>/dev/null || true)
  if [ -n "$out" ]; then echo "gigapose /health: $out"; break; fi
  sleep 3
done
