#!/bin/bash
# Zentex Frontend One-Click Restart Script
# Kills all frontend processes and restarts with full logging
set -euo pipefail

echo ">>> [Zentex] 正在执行前端一键重启程序..."

FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

echo ">>> 正在关闭现有前端服务 (Port: ${FRONTEND_PORT})..."

is_port_listening() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1 || \
  lsof -nP -i :"${port}" -t >/dev/null 2>&1
}

kill_port() {
  local port="$1"
  local attempt
  local pids
  local permission_denied=0
  for attempt in 1 2 3 4 5; do
    # Try both LISTEN state and all states
    pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [ -z "${pids}" ]; then
      # Also check for non-LISTEN states (CLOSED, TIME_WAIT, etc.)
      pids="$(lsof -nP -i :"${port}" -t 2>/dev/null || true)"
    fi
    if [ -z "${pids}" ]; then
      break
    fi
    echo ">>> 关闭占用端口 ${port} 的进程(第 ${attempt}/5 次): ${pids}"
    # First try graceful shutdown, then SIGKILL as a last resort.
    for pid in ${pids}; do
      if ! kill "${pid}" 2>/dev/null; then
        permission_denied=1
      fi
    done
    sleep 0.2
    if is_port_listening "${port}"; then
      echo ">>> 端口 ${port} 仍被占用，执行强制关闭(第 ${attempt}/5 次): ${pids}"
      for pid in ${pids}; do
        if ! kill -9 "${pid}" 2>/dev/null; then
          permission_denied=1
        fi
      done
      sleep 0.2
    fi
    if ! is_port_listening "${port}"; then
      break
    fi
  done

  if is_port_listening "${port}"; then
    echo ">>> [FAIL-CLOSED] 端口 ${port} 仍处于 LISTEN 状态，重启中止。"
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN || true
    if [ "${permission_denied}" -eq 1 ]; then
      echo ">>> [PERMISSION] 当前环境没有权限结束该端口进程（可能是终端/沙箱限制）。"
      echo ">>> 建议：在你启动它的那个终端里 Ctrl+C 结束，或手动执行："
      echo ">>>   sudo lsof -ti :${port} | xargs sudo kill -9"
      echo ">>> 或者临时改端口启动："
      echo ">>>   FRONTEND_PORT=5174 npm run dev"
    fi
    echo ">>> 请手动结束占用该端口的进程后重试："
    echo ">>>   lsof -nP -iTCP:${port} -sTCP:LISTEN"
    echo ">>>   kill -9 <PID>"
    exit 1
  fi
}

kill_port "${FRONTEND_PORT}"

# Kill any existing frontend processes
echo ">>> 清理残留的前端进程..."
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 2

# Secondary confirmation that port is released
echo ">>> 二次确认端口状态..."
if is_port_listening "${FRONTEND_PORT}"; then
  echo ">>> [WARN] 端口 ${FRONTEND_PORT} 仍被占用，尝试强制清理..."
  lsof -nP -i :${FRONTEND_PORT} -t | xargs kill -9 2>/dev/null || true
  sleep 3
fi

# Check if dependencies are installed
if [ ! -d "src/admin-portal/node_modules" ]; then
  echo ">>> admin-portal 依赖未安装。"
  echo ">>> 运行: make frontend-install"
  exit 1
fi

echo ">>> 前端环境已清理。正在重新启动前端服务..."
echo ">>> 前端日志将实时输出..."
echo "=========================================="

# Start frontend with full logging
cd src/admin-portal
VITE_BACKEND_PORT="$BACKEND_PORT" npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT"
