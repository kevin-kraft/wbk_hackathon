#!/usr/bin/env bash
# Durably (re)create the `wbk-perception` container on the gpu-server.
#
# WHY: the running wbk-perception baked its code into the image and used
# `restart=no`. The locateanything `use_cache=True` fix was delivered with a
# `docker cp` into the live container — which is EPHEMERAL: lost on any
# container recreate, and a gpu-server reboot both loses it AND leaves yolo /
# locateanything down (nothing auto-starts). This recreates the container from
# the same image but durably:
#   * canonical perception source BIND-MOUNTED from /mnt/vss-data/kip/perception
#     (which already carries the fixes) — future updates are just edit + restart,
#     no image rebuild;
#   * `--restart unless-stopped` — survives reboots;
#   * a supervisord config that runs ONLY yolo (:8001) + locateanything (:8003) —
#     the two services this container actually publishes. sam3 has its own
#     `wbk-sam3` container and yoloseg its own `wbk-yoloseg` sidecar, so we stop
#     double-loading those models on the GPU (the baked config wasted VRAM on a
#     shadow sam3);
#   * a supervisorctl control socket so a single program can be restarted
#     (`supervisorctl restart locateanything`) without bouncing yolo — the baked
#     config lacked this, which is why we had to pkill-respawn.
#
# RUN ON the gpu-server (bounces yolo + locateanything for a model reload — pick
# a quiet moment):
#   scp deploy/perception/redeploy-wbk-perception.sh gpu-server:/tmp/
#   ssh gpu-server 'bash /tmp/redeploy-wbk-perception.sh'
#
# Idempotent: safe to re-run. Config below matches the captured running config
# (image, GPU device 1, host ports 6767->8001 / 6769->8003, env, weights mounts).
set -euo pipefail

CODE=/mnt/vss-data/kip/perception
IMAGE=wbk-perception:blackwell
CONF="$CODE/supervisord.wbk-perception.conf"

echo "=== 1. sanity: canonical source carries the fixes ==="
test -f "$CODE/services/locateanything/model.py"
grep -q 'use_cache=True' "$CODE/services/locateanything/model.py" \
  || { echo "ERROR: $CODE locateanything missing use_cache fix — sync perception/ first."; exit 1; }
grep -q 'Access-Control-Allow-Origin' "$CODE/services/shared/app_factory.py" \
  || { echo "ERROR: $CODE app_factory missing CORS fix — sync perception/ first."; exit 1; }
echo "  ok: use_cache + CORS present in canonical source"

echo "=== 2. write wbk-perception supervisord config (yolo + locateanything only) ==="
cat > "$CONF" <<'CONF'
; wbk-perception: serves ONLY yolo (:8001) + locateanything (:8003).
; sam3 -> wbk-sam3 container; yoloseg -> wbk-yoloseg sidecar. Do not double-load.
[supervisord]
nodaemon=true
user=root
logfile=/dev/stdout
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

; Control socket: restart one program without bouncing the whole container.
[unix_http_server]
file=/tmp/supervisor.sock

[supervisorctl]
serverurl=unix:///tmp/supervisor.sock

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[program:yolo]
command=uvicorn services.yolo.main:app --host 0.0.0.0 --port 8001
directory=/app/perception
autorestart=true
startretries=3
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:locateanything]
command=uvicorn services.locateanything.main:app --host 0.0.0.0 --port 8003
directory=/app/perception
autorestart=true
startretries=3
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
CONF
echo "  wrote $CONF"

echo "=== 3. recreate the container (durable) ==="
docker rm -f wbk-perception >/dev/null 2>&1 || true
docker run -d --name wbk-perception \
  --restart unless-stopped \
  --gpus '"device=1"' \
  -p 127.0.0.1:6767:8001 \
  -p 127.0.0.1:6769:8003 \
  -e PERCEPTION_DEVICE=cuda \
  -e WEIGHTS_DIR=/weights \
  -e HF_HOME=/root/.cache/huggingface \
  -e YOLO_WEIGHTS=/weights/parts_detmask.pt \
  -e PYTHONUNBUFFERED=1 \
  -v /mnt/vss-data/kip/weights:/weights \
  -v /mnt/vss-data/kip/weights/hf-cache:/root/.cache/huggingface \
  -v "$CODE":/app/perception \
  -w /app/perception \
  "$IMAGE" \
  supervisord -c /app/perception/supervisord.wbk-perception.conf >/dev/null
echo "  container created"

echo "=== 4. wait for health (yolo :6767, locateanything :6769 — the 3B VLM is slow) ==="
for port in 6767 6769; do
  ok=""
  for i in $(seq 1 60); do
    out=$(curl -s --max-time 5 "http://127.0.0.1:${port}/health" 2>/dev/null || true)
    if echo "$out" | grep -q '"loaded":true'; then ok="$out"; break; fi
    sleep 3
  done
  echo "  :${port} -> ${ok:-TIMED OUT (check: docker logs wbk-perception)}"
done

echo "done. The locateanything fix is now durable (survives reboot + recreate)."
echo "Future code updates: edit /mnt/vss-data/kip/perception then"
echo "  docker exec wbk-perception supervisorctl -c /app/perception/supervisord.wbk-perception.conf restart locateanything"
