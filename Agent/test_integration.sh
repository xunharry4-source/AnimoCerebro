#!/bin/bash
# Test Agent Integration Script

set -e

echo "========================================="
echo "  Zentex Agent Integration Test"
echo "========================================="

cd /Users/harry/Documents/git/AnimoCerebro

# Step 1: Start Test Agents
echo ""
echo "📡 Step 1: Starting Test Agent Servers..."
python3 Agent/test_server.py > /tmp/test_agents.log 2>&1 &
AGENT_PID=$!
echo "   Test agents PID: $AGENT_PID"
sleep 3

# Verify test agents are running
if curl -s http://127.0.0.1:9001/status > /dev/null && curl -s http://127.0.0.1:9002/status > /dev/null; then
    echo "   ✅ Test agents started successfully"
else
    echo "   ❌ Failed to start test agents"
    cat /tmp/test_agents.log
    exit 1
fi

# Step 2: Start Zentex Backend
echo ""
echo "🧠 Step 2: Starting Zentex Backend..."
export PYTHONPATH=src
uvicorn zentex.web_console.dev_server:app --host 127.0.0.1 --port 8000 > /tmp/zentex_backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
sleep 5

# Verify backend is running
if curl -s http://127.0.0.1:8000/docs > /dev/null; then
    echo "   ✅ Zentex backend started successfully"
else
    echo "   ❌ Failed to start backend"
    tail -20 /tmp/zentex_backend.log
    kill $AGENT_PID $BACKEND_PID 2>/dev/null || true
    exit 1
fi

# Step 3: Register Calculator Agent
echo ""
echo "📝 Step 3: Registering Calculator Agent..."
CALC_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/web/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "agent-calculator",
    "agent_name": "Calculator Agent",
    "version": "1.0.0",
    "function_description": "Performs mathematical calculations",
    "endpoint": "http://127.0.0.1:9001",
    "auth_token": "",
    "role_tag": "calculator",
    "scope": ["math"]
  }')

echo "   Response: $CALC_RESPONSE"
CALC_AGENT_ID=$(echo $CALC_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['agent_id'])")
echo "   ✅ Calculator Agent registered with ID: $CALC_AGENT_ID"

# Step 4: Register Data Generator Agent
echo ""
echo "📝 Step 4: Registering Data Generator Agent..."
GEN_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/web/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "agent-data-generator",
    "agent_name": "Data Generator Agent",
    "version": "1.0.0",
    "function_description": "Generates random CSV data",
    "endpoint": "http://127.0.0.1:9002",
    "auth_token": "",
    "role_tag": "generator",
    "scope": ["data"]
  }')

echo "   Response: $GEN_RESPONSE"
GEN_AGENT_ID=$(echo $GEN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['agent_id'])")
echo "   ✅ Data Generator Agent registered with ID: $GEN_AGENT_ID"

# Step 5: Wait for Handshake
echo ""
echo "⏳ Step 5: Waiting for automatic handshake..."
sleep 3

# Step 6: List Registered Agents
echo ""
echo "📋 Step 6: Listing all registered agents..."
AGENTS_LIST=$(curl -s http://127.0.0.1:8000/api/web/agents)
echo "$AGENTS_LIST" | python3 -m json.tool

# Step 7: Check agent status
echo ""
echo "🔍 Step 7: Checking agent statuses..."
curl -s http://127.0.0.1:8000/api/web/agents/$CALC_AGENT_ID/handshake > /dev/null
echo "   Calculator Agent handshake triggered"

curl -s http://127.0.0.1:8000/api/web/agents/$GEN_AGENT_ID/handshake > /dev/null
echo "   Data Generator Agent handshake triggered"

sleep 2

# Final status check
echo ""
echo "✅ ========================================"
echo "  Integration Test Complete!"
echo "========================================="
echo ""
echo "Test agents are running on:"
echo "  - Calculator: http://127.0.0.1:9001"
echo "  - Data Generator: http://127.0.0.1:9002"
echo ""
echo "Zentex backend: http://127.0.0.1:8000"
echo "Web Console: http://127.0.0.1:5173"
echo ""
echo "PIDs:"
echo "  Test Agents: $AGENT_PID"
echo "  Backend: $BACKEND_PID"
echo ""
echo "To stop: kill $AGENT_PID $BACKEND_PID"
