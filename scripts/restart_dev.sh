#!/bin/bash
# Zentex Clinical Restart Script
# 清理占用端口的旧进程并重新启动 Web Console + Admin Portal
set -euo pipefail

echo ">>> [Zentex] 正在执行临床级重启程序..."

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

# 端口与 make dev 保持一致，可通过环境变量覆盖
PORT_BACKEND="${BACKEND_PORT:-8000}"
PORT_FRONTEND="${FRONTEND_PORT:-5173}"
WS_IMPLEMENTATION="${WS_IMPLEMENTATION:-websockets-sansio}"
export ZENTEX_WS_IMPLEMENTATION="${WS_IMPLEMENTATION}"

echo ">>> 正在关闭现有服务 (Ports: ${PORT_BACKEND}, ${PORT_FRONTEND})..."

is_port_listening() {
  local port="$1"
  # Check both LISTEN state and any process using the port
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
      echo ">>>   BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev"
    fi
    echo ">>> 请手动结束占用该端口的进程后重试："
    echo ">>>   lsof -nP -iTCP:${port} -sTCP:LISTEN"
    echo ">>>   kill -9 <PID>"
    exit 1
  fi
}

kill_port "${PORT_BACKEND}"
kill_port "${PORT_FRONTEND}"

# 兜底：只清理与本项目 Web Console 相关的 uvicorn（避免误杀其他 node/服务）
echo ">>> 清理残留的 uvicorn 和 node 进程..."
pkill -f "uvicorn zentex.web_console.dev_server:app" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true
sleep 2

# 二次确认端口已释放
echo ">>> 二次确认端口状态..."
if is_port_listening "${PORT_BACKEND}"; then
  echo ">>> [WARN] 端口 ${PORT_BACKEND} 仍被占用，尝试强制清理..."
  # Force kill all processes on this port (not just LISTEN)
  lsof -nP -i :${PORT_BACKEND} -t | xargs kill -9 2>/dev/null || true
  sleep 3
fi

if is_port_listening "${PORT_FRONTEND}"; then
  echo ">>> [WARN] 端口 ${PORT_FRONTEND} 仍被占用，尝试强制清理..."
  lsof -nP -i :${PORT_FRONTEND} -t | xargs kill -9 2>/dev/null || true
  sleep 3
fi

# 清理运行时大型文件，加速启动
RUNTIME_DIR=".zentex/runtime"
if [ -d "${RUNTIME_DIR}" ]; then
  echo ">>> 正在清理运行时大型文件以加速启动..."
  # 保留必要目录结构，但清空大文件
  for large_file in enhanced_episodic.jsonl enhanced_semantic.jsonl enhanced_memory_audit.jsonl enhanced_procedural.jsonl enhanced_management.json web_console_transcript.jsonl brain_transcript.jsonl; do
    filepath="${RUNTIME_DIR}/${large_file}"
    if [ -f "${filepath}" ]; then
      file_size=$(stat -f%z "${filepath}" 2>/dev/null || echo "0")
      if [ "${file_size}" -gt 1048576 ]; then  # 大于1MB的文件
        echo ">>> 清空大文件: ${large_file} (${file_size} bytes)"
        > "${filepath}"
      fi
    fi
  done
fi

echo ">>> 环境已清理。正在通过 'make dev' 重新拉起 Zentex 系统..."

# NOTE: Skip heavy check-startup validation in restart flow since uvicorn will
# initialize the full app anyway. This avoids double initialization with 1.5GB+ files.

make dev
