#!/usr/bin/env bash
set -euo pipefail

JETSON_PROJECT_ROOT="/home/lara5/Neura_Ben/ki_robotik_cv_seminar"
JETSON_BACKEND_ROOT="$JETSON_PROJECT_ROOT/jetson_backend"

set -a
source "$JETSON_PROJECT_ROOT/.env"
set +a

VENV_PY="$JETSON_BACKEND_ROOT/.venv/bin/python"

API_HOST="${JETSON_API_HOST:-0.0.0.0}"
API_PORT="${JETSON_API_PORT:-8000}"

export PYTHONPATH="$JETSON_PROJECT_ROOT:$JETSON_BACKEND_ROOT:${PYTHONPATH:-}"



cleanup() {
  echo "Stopping Jetson backend..."

  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo "Starting Jetson API..."
cd "$JETSON_BACKEND_ROOT"

"$VENV_PY" -m uvicorn app.main:app \
  --host "$API_HOST" \
  --port "$API_PORT" &
API_PID=$!

wait