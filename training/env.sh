# Source before any converter/training run on gpu-server.
#   source /mnt/vss-data/kip/code/env.sh
#
# The server's root disk (/, and thus /tmp and ~/.config, ~/.cache) is ~97% full.
# Redirect every temp dir and framework cache onto the 3.3 TB network drive so
# nothing writes to root. Without this, ultralytics/torch/pip fail with
# "No space left on device".
KIP=/mnt/vss-data/kip

export TMPDIR="$KIP/.tmp"
export PIP_CACHE_DIR="$KIP/.pip-cache"
export YOLO_CONFIG_DIR="$KIP/.ultralytics"     # ultralytics settings + runs config
export MPLCONFIGDIR="$KIP/.mpl"                 # matplotlib
export TORCH_HOME="$KIP/.torch"                 # torch hub cache
export HF_HOME="$KIP/.hf"                        # any HF downloads
export XDG_CACHE_HOME="$KIP/.cache"            # generic cache fallback
export ULTRALYTICS_DIR="$KIP/.ultralytics"

mkdir -p "$TMPDIR" "$PIP_CACHE_DIR" "$YOLO_CONFIG_DIR" "$MPLCONFIGDIR" \
         "$TORCH_HOME" "$HF_HOME" "$XDG_CACHE_HOME"

# Activate the venv if not already active.
if [ -z "${VIRTUAL_ENV:-}" ]; then
    # shellcheck disable=SC1091
    source "$KIP/venv/yolo/bin/activate"
fi
