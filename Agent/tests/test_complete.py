#!/usr/bin/env python3
"""
Complete Agent Integration Test
Tests Zentex Agent API endpoints and external Agent servers
"""
import requests
import time
import sys
import json

BASE_URL = "http://127.0.0.1:8000"
AGENT_1_PORT = 9001
AGENT_2_PORT = 9002

def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def test_zentex_agent_api():
    """Test 1: Verify Zentex Agent management API is working"""
    print_section("TEST 1: Zentex Agent API Endpoints")
    
    # Test 1.1: Check backend health
    print("\n1.1 Checking Zentex backend...")
    try:
        resp = requests.get(f"{BASE_URL}/api/web/overview", timeout=5)
        if resp.status_code == 200:
            print("   ✅ Backend is running")
        else:
            print(f"   ❌ Backend returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Cannot connect: {e}")
        return False
    
    # Test 1.2: List agents endpoint
    print("\n1.2 Testing GET /api/web/agents...")
    try:
        resp = requests.get(f"{BASE_URL}/api/web/agents", timeout=5)
        if resp.status_code == 200:
            agents = resp.json()
            print(f"   ✅ Endpoint working. Found {len(agents)} agent(s)")
            for agent in agents[:3]:  # Show first 3
                print(f"      - {agent.get('agent_name', 'N/A')} (Status: {agent.get('status', 'N/A')})")
        else:
            print(f"   ❌ Failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 1.3: Register a test agent
    print("\n1.3 Testing POST /api/web/agents/register...")
    test_agent = {
        "name": "test-agent-api",
        "agent_name": "API Test Agent",
        "version": "1.0.0",
        "function_description": "Testing API registration",
        "endpoint": f"http://127.0.0.1:{AGENT_1_PORT}",
        "auth_token": "",
        "role_tag": "test",
        "scope": ["test"]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/api/web/agents/register", json=test_agent, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            agent_id = data.get('agent_id')
            print(f"   ✅ Registration successful! Agent ID: {agent_id}")
            print(f"      Status: {data.get('status')}")
            print(f"      Trust Level: {data.get('trust_level')}")
            return agent_id
        else:
            print(f"   ❌ Registration failed: {resp.status_code}")
            print(f"      Response: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def test_external_agent_server(port, name):
    """Test 2: Verify external Agent server is responding"""
    print_section(f"TEST 2: External Agent Server ({name} - Port {port})")
    
    base = f"http://127.0.0.1:{port}"
    
    # Test 2.1: Health check
    print(f"\n2.1 Testing {base}/status...")
    try:
        resp = requests.get(f"{base}/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"   ✅ Status endpoint working")
            print(f"      Response: {json.dumps(data, indent=6)}")
        else:
            print(f"   ❌ Failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 2.2: Handshake endpoint
    print(f"\n2.2 Testing {base}/handshake...")
    try:
        resp = requests.post(f"{base}/handshake", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"   ✅ Handshake endpoint working")
            print(f"      Agent ID: {data.get('agent_id')}")
            print(f"      Version: {data.get('version')}")
            print(f"      Capabilities: {len(data.get('capabilities', []))} found")
            return True
        else:
            print(f"   ❌ Failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_handshake_integration(agent_id):
    """Test 3: Test handshake between Zentex and external Agent"""
    print_section("TEST 3: Zentex ↔ External Agent Handshake")
    
    if not agent_id:
        print("   ⚠️  Skipping: No agent registered")
        return False
    
    print(f"\n3.1 Triggering handshake for agent {agent_id}...")
    try:
        resp = requests.get(f"{BASE_URL}/api/web/agents/{agent_id}/handshake", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get('status')
            print(f"   ✅ Handshake completed!")
            print(f"      Agent Status: {status}")
            print(f"      Capabilities: {len(data.get('capabilities', []))} discovered")
            
            if status in ['idle', 'active']:
                print(f"      🎉 Agent is ready for tasks!")
                return True
            else:
                print(f"      ⚠️  Agent status is {status}, may need attention")
                return False
        else:
            print(f"   ❌ Handshake failed: {resp.status_code}")
            print(f"      Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"   ❌ Error during handshake: {e}")
        return False

def test_cross_agent_communication():
    """Test 4: Test interaction between two external Agents"""
    print_section("TEST 4: Cross-Agent Communication")
    
    print("\n4.1 Testing Calculator Agent (9001)...")
    calc_payload = {
        "task_id": "test-001",
        "action": "calculate",
        "params": {"operation": "add", "a": 10, "b": 5}
    }
    
    try:
        resp = requests.post(f"http://127.0.0.1:{AGENT_1_PORT}/execute", json=calc_payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"   ✅ Calculator Agent executed task")
            print(f"      Result: {data.get('result')}")
        else:
            print(f"   ❌ Failed: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n4.2 Testing Data Generator Agent (9002)...")
    gen_payload = {
        "task_id": "test-002",
        "action": "generate",
        "params": {"rows": 5, "filename": "test_cross.csv"}
    }
    
    try:
        resp = requests.post(f"http://127.0.0.1:{AGENT_2_PORT}/execute", json=gen_payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"   ✅ Data Generator Agent executed task")
            if data.get('result', {}).get('success'):
                print(f"      Generated file: {data['result'].get('filepath')}")
                print(f"      Rows: {data['result'].get('rows_generated')}")
        else:
            print(f"   ❌ Failed: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

def main():
    print("\n" + "🧪" * 35)
    print("  ZENTEX AGENT INTEGRATION TEST SUITE")
    print("🧪" * 35)
    
    # Test 1: Zentex API
    agent_id = test_zentex_agent_api()
    
    # Test 2: External Agent Servers
    calc_ok = test_external_agent_server(AGENT_1_PORT, "Calculator")
    gen_ok = test_external_agent_server(AGENT_2_PORT, "Data Generator")
    
    if not (calc_ok and gen_ok):
        print("\n⚠️  External Agent servers are not running.")
        print("   Start them with: .venv/bin/python Agent/test_server.py")
        return False
    
    # Test 3: Handshake Integration
    handshake_ok = test_handshake_integration(agent_id)
    
    # Test 4: Cross-Agent Communication
    test_cross_agent_communication()
    
    # Summary
    print_section("TEST SUMMARY")
    print(f"\n✅ Zentex API: {'PASS' if agent_id else 'FAIL'}")
    print(f"✅ Calculator Agent: {'PASS' if calc_ok else 'FAIL'}")
    print(f"✅ Data Generator Agent: {'PASS' if gen_ok else 'FAIL'}")
    print(f"✅ Handshake Integration: {'PASS' if handshake_ok else 'FAIL'}")
    
    all_pass = agent_id and calc_ok and gen_ok and handshake_ok
    
    print("\n" + "=" * 70)
    if all_pass:
        print("  🎉 ALL TESTS PASSED! Agent integration is working correctly.")
    else:
        print("  ⚠️  Some tests failed. Check the output above for details.")
    print("=" * 70 + "\n")
    
    return all_pass

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
