#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/2] Running Python tests"
pytest test tests

echo "[2/2] Running admin-portal tests"
if [ ! -f "src/admin-portal/package.json" ]; then
  echo "Missing src/admin-portal/package.json"
  exit 1
fi

if [ ! -d "src/admin-portal/node_modules" ]; then
  echo "admin-portal dependencies are not installed."
  echo "Run: make frontend-install"
  exit 1
fi

cd src/admin-portal
npm run test
