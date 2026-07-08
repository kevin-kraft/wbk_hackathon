#!/usr/bin/env bash
# Swap the wbk-perception `yolo` detection model from the sim-trained detector
# (parts_detmask.pt, YOLOv26m on synthetic Isaac data) to the REAL-photo-trained
# LARA5 detector (Gruppe4 `yolo26x_seg_lara5`, best.pt) to close the sim-to-real
# gap. The seg model serves boxes via the same /infer contract (result.boxes),
# and additionally carries masks for free.
#
# Best real-world scores (held-out real photos): box mAP50 0.830 / mAP50-95 0.717
# vs the RT-DETR det candidate at 0.767 — this seg model is the strongest boxer.
#
# PRE-STAGED (already done from the laptop, md5 7161eb51a2ccf12e26cf3e37e7f1e124):
#   gpu-server:/tmp/yolo26x_seg_lara5_best.pt   (the new weights, 136M)
#   gpu-server:/tmp/real_test.png               (a real LARA5 Zivid frame)
#
# Validation is done through the LIVE serving path (uvicorn under supervisord has
# a working conda env; a bare `docker exec python` does not). If the service does
# not come up healthy after the swap, the script AUTO-ROLLS-BACK to the sim model.
#
# RUN ON the gpu-server:
#   scp deploy/perception/swap-yolo-real-weights.sh gpu-server:/tmp/
#   ssh gpu-server 'bash /tmp/swap-yolo-real-weights.sh'
set -euo pipefail

WDIR=/mnt/vss-data/kip/weights
NEW_SRC=/tmp/yolo26x_seg_lara5_best.pt
NEW_STAGED="$WDIR/parts_real_yolo26xseg.pt"
LIVE="$WDIR/parts_detmask.pt"          # what YOLO_WEIGHTS points at (env unchanged)
TEST_IMG=/tmp/real_test.png
EXPECT_MD5=7161eb51a2ccf12e26cf3e37e7f1e124
STAMP=$(date +%Y%m%d-%H%M%S)
BAK="$WDIR/parts_detmask.pt.sim-bak-$STAMP"
SUP="supervisorctl -c /app/perception/supervisord.wbk-perception.conf"

restart_yolo() { docker exec wbk-perception $SUP restart yolo >/dev/null; }
wait_health() {  # echoes health json if loaded:true within ~80s, else returns 1
  for _ in $(seq 1 40); do
    out=$(curl -s --max-time 5 http://127.0.0.1:6767/health 2>/dev/null || true)
    if echo "$out" | grep -q '"loaded":true'; then echo "$out"; return 0; fi
    sleep 2
  done
  return 1
}

echo "=== 0. preconditions ==="
test -f "$NEW_SRC" || { echo "ERROR: $NEW_SRC missing (scp it from the laptop first)"; exit 1; }
got=$(md5sum "$NEW_SRC" | awk '{print $1}')
[ "$got" = "$EXPECT_MD5" ] || { echo "ERROR: md5 mismatch on $NEW_SRC ($got != $EXPECT_MD5)"; exit 1; }
test -f "$LIVE" || { echo "ERROR: live weights $LIVE not found"; exit 1; }
echo "  ok: new weights present + checksum verified; live weights present"

echo "=== 1. stage new weights + back up current (sim) weights ==="
cp "$NEW_SRC" "$NEW_STAGED"
cp "$LIVE" "$BAK"
echo "  staged: $NEW_STAGED"
echo "  backup: $BAK"

echo "=== 2. swap live weights (YOLO_WEIGHTS env unchanged) + restart yolo ==="
cp "$NEW_STAGED" "$LIVE"
ls -la "$LIVE"
restart_yolo

echo "=== 3. wait for the real model to load in the live service ==="
if health=$(wait_health); then
  echo "  /health -> $health"
else
  echo "  !! yolo did NOT report loaded:true — AUTO-ROLLBACK to sim weights"
  cp "$BAK" "$LIVE"; restart_yolo
  wait_health >/dev/null && echo "  rolled back; sim model healthy again" || echo "  ROLLBACK ALSO UNHEALTHY — check: docker logs wbk-perception"
  exit 1
fi

echo "=== 4. live /infer smoke test on a REAL photo (host-side curl) ==="
TOKEN=$(docker exec wbk-perception sh -c 'tr "\0" "\n" < /proc/1/environ | grep "^WBK_API_TOKEN=" | cut -d= -f2-' 2>/dev/null || true)
AUTH=(); [ -n "$TOKEN" ] && AUTH=(-H "Authorization: Bearer $TOKEN")
B64=$(base64 -w0 "$TEST_IMG")
RESP=$(printf '{"image_b64":"%s","conf":0.25}' "$B64" | \
  curl -s --max-time 90 -X POST http://127.0.0.1:6767/infer \
    -H "Content-Type: application/json" "${AUTH[@]}" --data-binary @- 2>/dev/null || true)
echo "$RESP" | /usr/bin/python3 - <<'PY' 2>/dev/null || echo "  (raw) ${RESP:0:200}"
import sys, json
from collections import Counter
try:
    r = json.load(sys.stdin)
except Exception as e:
    print("  could not parse /infer response:", e); sys.exit(0)
dets = r.get("detections", [])
print("  model:", r.get("model"), "inference_ms:", r.get("inference_ms"),
      "size:", f'{r.get("width")}x{r.get("height")}', "n_detections:", len(dets))
for label, n in Counter(d.get("label") for d in dets).most_common(15):
    print(f"    {label}: {n}")
PY

echo
echo "DONE. Real-photo LARA5 detector is now live on yolo (:6767 / local :18001)."
echo "ROLLBACK if needed:"
echo "  cp $BAK $LIVE && docker exec wbk-perception $SUP restart yolo"
