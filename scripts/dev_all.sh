#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Starting Zentex web console"

PYTHON_BIN="python3"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
WS_IMPLEMENTATION="${WS_IMPLEMENTATION:-websockets-sansio}"
export ZENTEX_WS_IMPLEMENTATION="${WS_IMPLEMENTATION}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

if [ ! -d "src/admin-portal/node_modules" ]; then
  echo "admin-portal dependencies are not installed."
  echo "Run: make frontend-install"
  exit 1
fi

if lsof -nP -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "Backend port already in use: ${BACKEND_PORT}"
  echo "Run: make restart-dev"
  exit 1
fi

if lsof -nP -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "Frontend port already in use: ${FRONTEND_PORT}"
  echo "Run: make restart-dev"
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY'
import importlib
import importlib.util
required = ("fastapi", "pydantic", "uvicorn")
websocket_runtime = ("websockets", "wsproto")
for mod in required:
    importlib.import_module(mod)
if not any(importlib.util.find_spec(mod) is not None for mod in websocket_runtime):
    raise ModuleNotFoundError("websocket runtime missing")
PY
then
  echo "Backend dependencies missing (see requirements.txt)."
  echo "Create a local virtualenv and install dependencies there:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt"
  exit 1
fi

echo "Starting backend on http://127.0.0.1:${BACKEND_PORT}"
echo "Using WebSocket implementation: ${WS_IMPLEMENTATION}"
(
  export PYTHONPATH=src
  # Add a small delay to ensure port is fully released
  sleep 1
  "$PYTHON_BIN" -m uvicorn zentex.boot.web_dev:app --reload --ws "$WS_IMPLEMENTATION" --host 127.0.0.1 --port "$BACKEND_PORT" --timeout-keep-alive 5
) &
BACKEND_PID=$!

echo "Waiting for backend health (max 30 seconds)..."
BACKEND_READY=0
for i in {1..30}; do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/web/overview" >/dev/null 2>&1; then
    BACKEND_READY=1
    echo "Backend is ready after ${i} seconds"
    break
  fi
  
  # Check if backend process is still running
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "ERROR: Backend process died unexpectedly"
    exit 1
  fi
  
  sleep 1
done

if [ "$BACKEND_READY" -ne 1 ]; then
  echo "Backend failed readiness check: http://127.0.0.1:${BACKEND_PORT}/api/web/overview"
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  exit 1
fi

echo "Starting frontend on http://127.0.0.1:${FRONTEND_PORT}"
(cd src/admin-portal && VITE_BACKEND_PORT="$BACKEND_PORT" npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  kill "$FRONTEND_PID" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

echo "Web console is starting:"
echo "  Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "  Backend:  http://127.0.0.1:${BACKEND_PORT}"
echo "  API:      http://127.0.0.1:${BACKEND_PORT}/api/web/plugins/cognitive"

wait "$BACKEND_PID" "$FRONTEND_PID"
