#!/usr/bin/env bash
# Timing probe: run a few epochs of det (GPU 0) and seg (GPU 2) in parallel at
# the real training settings, then read steady-state sec/epoch from results.csv
# and compute the epoch count that fits a wall-clock budget.
set -uo pipefail
# shellcheck disable=SC1091
source /mnt/vss-data/kip/code/env.sh
cd /mnt/vss-data/kip/code

HOURS="${HOURS:-4}"
OVERHEAD_S="${OVERHEAD_S:-600}"      # scan + warmup + final val/export margin
PROBE_EPOCHS="${PROBE_EPOCHS:-4}"
IMGSZ="${IMGSZ:-1536}"
BATCH="${BATCH:-16}"
DET_DEVICE="${DET_DEVICE:-0}"        # pick idle GPUs (check nvidia-smi first)
SEG_DEVICE="${SEG_DEVICE:-6}"
RUNS=/mnt/vss-data/kip/runs

echo "[probe] det (GPU$DET_DEVICE) + seg (GPU$SEG_DEVICE), $PROBE_EPOCHS epochs, imgsz=$IMGSZ batch=$BATCH"

rm -rf "$RUNS/_probe_det" "$RUNS/_probe_seg"

# --amp false: AMP autocast triggers a CUDA illegal-memory-access in validation
# on the RTX PRO 6000 Blackwell + torch-2.12 stack (fp32 works fine).
python train.py --data /mnt/vss-data/kip/datasets/parts_det/data.yaml \
  --model yolo26m.pt --name _probe_det --device "$DET_DEVICE" --amp false \
  --epochs "$PROBE_EPOCHS" --imgsz "$IMGSZ" --batch "$BATCH" \
  --save-period 0 --keep-last 0 --patience 1000 \
  > "$RUNS/_probe_det.log" 2>&1 &
PID_DET=$!

python train.py --data /mnt/vss-data/kip/datasets/parts_seg/data.yaml \
  --model yolo26m-seg.pt --name _probe_seg --device "$SEG_DEVICE" --amp false \
  --epochs "$PROBE_EPOCHS" --imgsz "$IMGSZ" --batch "$BATCH" \
  --save-period 0 --keep-last 0 --patience 1000 \
  > "$RUNS/_probe_seg.log" 2>&1 &
PID_SEG=$!

echo "[probe] det pid=$PID_DET seg pid=$PID_SEG — waiting ..."
wait $PID_DET; DET_RC=$?
wait $PID_SEG; SEG_RC=$?
echo "[probe] det rc=$DET_RC seg rc=$SEG_RC"

python - "$HOURS" "$OVERHEAD_S" "$RUNS/_probe_det/results.csv" "$RUNS/_probe_seg/results.csv" <<'PY'
import csv, math, sys
hours = float(sys.argv[1]); overhead = float(sys.argv[2])
def per_epoch(path):
    try:
        rows = list(csv.DictReader(open(path)))
    except FileNotFoundError:
        return None
    tkey = next((k for k in rows[0] if k.strip() == "time"), None) if rows else None
    if not tkey or len(rows) < 2:
        return None
    times = [float(r[tkey]) for r in rows]
    diffs = [b - a for a, b in zip(times, times[1:])]
    return diffs
def summarize(name, path):
    diffs = per_epoch(path)
    print(f"\n=== {name} ===")
    if not diffs:
        print(f"  no timing (check {path%() if False else path})"); return
    print("  per-epoch seconds:", [round(d,1) for d in diffs])
    steady = diffs[1:] if len(diffs) > 1 else diffs   # drop epoch 1 (warmup)
    spe = sorted(steady)[len(steady)//2]              # median
    budget = hours*3600 - overhead
    epochs = max(1, math.floor(budget / spe))
    eta_min = (epochs*spe + overhead)/60
    print(f"  steady sec/epoch (median): {spe:.1f}")
    print(f"  budget: {hours}h - {overhead/60:.0f}min overhead = {budget/60:.0f} train-min")
    print(f"  => EPOCHS = {epochs}   (est total ~{eta_min:.0f} min = {eta_min/60:.2f} h)")
summarize("DETECTION (yolo26m)", sys.argv[3])
summarize("SEGMENTATION (yolo26m-seg)", sys.argv[4])
PY

echo "[probe] --- tail det log ---"; tail -3 "$RUNS/_probe_det.log"
echo "[probe] --- tail seg log ---"; tail -3 "$RUNS/_probe_seg.log"
echo "[probe] --- GPU mem during/after ---"; nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
