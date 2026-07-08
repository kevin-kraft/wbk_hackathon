#!/usr/bin/env bash
# Provision the training venv on the shared GPU server, on the network drive.
#
# The server has a WORKING Blackwell-capable torch system-wide
# (torch 2.12.1+cu132, CUDA available) — we reuse it via --system-site-packages
# rather than letting pip pull a torch that won't run on RTX PRO 6000. Only
# ultralytics (+ its non-torch deps) go into the venv.
#
# Per the gpu-server convention (wiki: gpu-server-access): plain venv + pip on
# THIS box (not uv). Everything lives under the network drive so the 97%-full
# root disk is untouched.
#
# Usage (on the server, or via ssh gpu-server 'bash -s' < setup_server.sh):
#   bash setup_server.sh
set -euo pipefail

KIP=/mnt/vss-data/kip
VENV="$KIP/venv/yolo"

# The root disk (and thus /tmp) is ~97% full — force all temp + caches onto the
# network drive, or pip fails with "No usable temporary directory found".
export TMPDIR="$KIP/.tmp"
export PIP_CACHE_DIR="$KIP/.pip-cache"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR"

echo "[setup] python: $(python3 --version)"
echo "[setup] TMPDIR=$TMPDIR"
echo "[setup] creating venv (system-site-packages) at $VENV"
python3 -m venv --system-site-packages "$VENV"
# keep pip caches off the root disk too
export PIP_CACHE_DIR="$KIP/.pip-cache"
"$VENV/bin/pip" install --upgrade pip >/dev/null

echo "[setup] installing ultralytics + tensorboard (torch reused from system site-packages)"
"$VENV/bin/pip" install "ultralytics>=8.4.0" "tensorboard>=2.16"
# --system-site-packages exposes an old system matplotlib built against a
# different numpy -> "numpy.core.multiarray failed to import". Install the
# numpy-dependent viz/science stack INTO the venv so it matches the venv numpy.
"$VENV/bin/pip" install --upgrade matplotlib pandas scipy

echo "[setup] verifying torch+cuda still resolve inside the venv"
# shellcheck disable=SC1091
source "$KIP/code/env.sh"
"$VENV/bin/python" - <<'PY'
import torch, ultralytics
print("torch", torch.__version__, "cuda", torch.cuda.is_available(),
      "devices", torch.cuda.device_count())
print("ultralytics", ultralytics.__version__)
PY

echo "[setup] done. activate with: source $VENV/bin/activate"
