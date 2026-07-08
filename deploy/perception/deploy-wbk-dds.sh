#!/usr/bin/env bash
# Deploy the `wbk-dds` sidecar on the gpu-server — a proxy for the DeepDataSpace
# cloud detectors (T-Rex2 / DINO-X / Grounding-DINO / DINO-XSeek) so they can be
# tested/compared against the local yolo/sam3/locateanything stack on the same
# frames.
#
# WHY a separate container (not a wbk-perception program):
#   * DDS runs in IDEA's cloud — this service is a CPU-only HTTP client with NO
#     torch/CUDA and NO GPU slot. It builds from a tiny python:slim image
#     (Dockerfile.dds), so it does not need the ~8 GB CUDA image or a rebuild of
#     wbk-perception, and it can be added/removed without touching the GPU
#     services.
#   * Source is BIND-MOUNTED from the canonical /mnt/vss-data/kip/perception, so
#     code updates are `rsync perception/ -> box` + `docker restart wbk-dds`.
#
# SECRETS: DDS needs an API token, and our routes are gated by WBK_API_TOKEN.
# Pass both via the environment when invoking (do NOT commit them):
#   DDS_API_TOKEN=xxxx WBK_API_TOKEN=yyyy \
#     ssh gpu-server 'DDS_API_TOKEN=xxxx WBK_API_TOKEN=yyyy bash /tmp/deploy-wbk-dds.sh'
# Typical flow from the repo root:
#   rsync -a perception/ gpu-server:/mnt/vss-data/kip/perception/
#   scp deploy/perception/deploy-wbk-dds.sh gpu-server:/tmp/
#   ssh gpu-server 'DDS_API_TOKEN=... WBK_API_TOKEN=... bash /tmp/deploy-wbk-dds.sh'
#
# Reach it from the dashboard host over an SSH tunnel (mirrors 18001-18007):
#   ssh -L 18008:localhost:6771 gpu-server   # then http://localhost:18008
#
# Idempotent: safe to re-run (rebuilds the image, recreates the container).
set -euo pipefail

CODE=/mnt/vss-data/kip/perception
IMAGE=wbk-dds:latest
HOST_PORT=6771   # -> container 8008 (6767/6769/6770 already taken; 8001 is another team's)

: "${DDS_API_TOKEN:?set DDS_API_TOKEN (get one at https://cloud.deepdataspace.com)}"
WBK_API_TOKEN="${WBK_API_TOKEN:-}"   # optional; empty disables bearer auth on this service

echo "=== 1. sanity: canonical source carries the dds service ==="
test -f "$CODE/services/dds/main.py"
test -f "$CODE/Dockerfile.dds"
test -f "$CODE/requirements-dds.txt"
echo "  ok: dds service present in $CODE"

echo "=== 2. build the slim CPU image ==="
docker build -f "$CODE/Dockerfile.dds" -t "$IMAGE" "$CODE"
echo "  built $IMAGE"

echo "=== 3. (re)create the container (CPU-only, durable) ==="
docker rm -f wbk-dds >/dev/null 2>&1 || true
docker run -d --name wbk-dds \
  --restart unless-stopped \
  -p 127.0.0.1:${HOST_PORT}:8008 \
  -e DDS_API_TOKEN="$DDS_API_TOKEN" \
  -e WBK_API_TOKEN="$WBK_API_TOKEN" \
  -e DDS_DEFAULT_MODEL="${DDS_DEFAULT_MODEL:-DINO-X-1.0}" \
  -e PYTHONUNBUFFERED=1 \
  -v "$CODE":/app/perception \
  -w /app/perception \
  "$IMAGE" >/dev/null
echo "  container created (host 127.0.0.1:${HOST_PORT} -> 8008)"

echo "=== 4. wait for health ==="
ok=""
for i in $(seq 1 20); do
  out=$(curl -s --max-time 5 "http://127.0.0.1:${HOST_PORT}/health" 2>/dev/null || true)
  if echo "$out" | grep -q '"status"'; then ok="$out"; break; fi
  sleep 2
done
echo "  :${HOST_PORT} -> ${ok:-TIMED OUT (check: docker logs wbk-dds)}"

echo "done. Smoke test (text prompt via DINO-X):"
echo "  IMG=\$(base64 -w0 frame.jpg)"
echo "  curl -s localhost:${HOST_PORT}/infer -H 'content-type: application/json' \\"
echo "    -H 'authorization: Bearer \$WBK_API_TOKEN' \\"
echo "    -d \"{\\\"image_b64\\\":\\\"\$IMG\\\",\\\"model\\\":\\\"DINO-X-1.0\\\",\\\"text\\\":\\\"gear . screw . bracket\\\"}\" | jq '.detections[:3]'"
