#!/bin/bash
# 启动 Calculator Agent
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "========================================="
echo "  Starting Calculator Agent"
echo "========================================="

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

echo ""
echo "📊 Calculator Agent Info:"
$PYTHON_BIN -c "
import sys
sys.path.insert(0, '.')
from Agent.calculator_agent import calculator_agent

info = calculator_agent.get_info()
print(f\"   ID: {info['agent_id']}\")
print(f\"   Name: {info['name']}\")
print(f\"   Status: {info['status']}\")
print(f\"   Capabilities: {', '.join(info['capabilities'])}\")
print()
print('   Testing calculations:')

tests = [
    ('add', 10, 5),
    ('subtract', 20, 8),
    ('multiply', 6, 7),
    ('divide', 100, 4),
    ('power', 2, 8),
]

for op, a, b in tests:
    result = calculator_agent.calculate(op, a, b)
    if result['success']:
        print(f\"   ✓ {a} {op} {b} = {result['result']}\")
    else:
        print(f\"   ✗ {op} failed: {result.get('error')}\")
"

echo ""
echo "✅ Calculator Agent is ready!"
echo "========================================="
