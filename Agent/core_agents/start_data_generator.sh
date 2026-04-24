#!/bin/bash
# 启动 Data Generator Agent
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "========================================="
echo "  Starting Data Generator Agent"
echo "========================================="

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

echo ""
echo "📁 Data Generator Agent Info:"
$PYTHON_BIN -c "
import sys
sys.path.insert(0, '.')
from Agent.data_generator_agent import data_generator_agent

info = data_generator_agent.get_info()
print(f\"   ID: {info['agent_id']}\")
print(f\"   Name: {info['name']}\")
print(f\"   Status: {info['status']}\")
print(f\"   Capabilities: {', '.join(info['capabilities'])}\")
print(f\"   Testdata Directory: {info['testdata_directory']}\")
print()
print('   Generating CSV file with 10 random rows...')

csv_result = data_generator_agent.generate_csv(
    filename='agent_generated_data.csv',
    num_rows=10
)

if csv_result['success']:
    print(f\"   ✓ CSV generated successfully!\")
    print(f\"   File: {csv_result['filepath']}\")
    print(f\"   Rows: {csv_result['rows_generated']}\")
else:
    print(f\"   ✗ Failed to generate CSV: {csv_result.get('error')}\")
"

echo ""
echo "✅ Data Generator Agent is ready!"
echo "========================================="
