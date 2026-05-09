#!/bin/zsh
set -euo pipefail

# Zentex 一键依赖安装脚本（后端 .venv + 前端 npm）
# 入口：make install 或 ./scripts/setup_env.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

require_cmd() {
  local name="$1"
  local hint="$2"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo ">>> [FAIL] 未找到命令: ${name}"
    echo ">>> ${hint}"
    exit 1
  fi
}

echo ">>> [Zentex] 开始一键安装全栈依赖..."

require_cmd python3 "请安装 Python 3，并确保 python3 在 PATH 中。"
require_cmd node "请安装 Node.js（建议 LTS），并确保 node 在 PATH 中。"
require_cmd npm "请安装 npm（通常随 Node 提供），并确保 npm 在 PATH 中。"

# 1. 后端依赖
echo ">>> [1/2] 正在创建/复用 Python 虚拟环境并安装后端依赖..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

# 2. 前端依赖
echo ">>> [2/2] 正在安装前端 Admin Portal 依赖 (npm install)..."
if [ -d "src/admin-portal" ]; then
  (cd src/admin-portal && npm install)
else
  echo ">>> [WARN] 未找到 src/admin-portal，已跳过前端安装。"
fi

echo ">>> [DONE] 依赖安装完成。"
echo ">>> 下一步：make dev（或 ./scripts/dev_all.sh）启动开发环境。"
