"""
Quick Integration Test - Register and Verify Agents
"""
import requests
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_agent_integration():
    print("=" * 60)
    print("Zentex Agent Integration Test")
    print("=" * 60)
    
    # Step 1: Check if backend is running
    print("\n1️⃣  Checking Zentex backend...")
    try:
        resp = requests.get(f"{BASE_URL}/api/web/overview", timeout=5)
        if resp.status_code == 200:
            print("   ✅ Backend is running")
        else:
            print(f"   ❌ Backend returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Cannot connect to backend: {e}")
        print("   Please start Zentex first: make dev")
        return False
    
    # Step 2: Register Calculator Agent
    print("\n2️⃣  Registering Calculator Agent (port 9001)...")
    calc_payload = {
        "name": "agent-calculator",
        "agent_name": "Calculator Agent",
        "version": "1.0.0",
        "function_description": "Performs mathematical calculations",
        "endpoint": "http://127.0.0.1:9001",
        "auth_token": "",
        "role_tag": "calculator",
        "scope": ["math"]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/api/web/agents/register", json=calc_payload, timeout=10)
        if resp.status_code == 200:
            calc_data = resp.json()
            calc_id = calc_data['agent_id']
            print(f"   ✅ Registered! Agent ID: {calc_id}")
        else:
            print(f"   ❌ Registration failed: {resp.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Step 3: Register Data Generator Agent
    print("\n3️⃣  Registering Data Generator Agent (port 9002)...")
    gen_payload = {
        "name": "agent-data-generator",
        "agent_name": "Data Generator Agent",
        "version": "1.0.0",
        "function_description": "Generates random CSV data",
        "endpoint": "http://127.0.0.1:9002",
        "auth_token": "",
        "role_tag": "generator",
        "scope": ["data"]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/api/web/agents/register", json=gen_payload, timeout=10)
        if resp.status_code == 200:
            gen_data = resp.json()
            gen_id = gen_data['agent_id']
            print(f"   ✅ Registered! Agent ID: {gen_id}")
        else:
            print(f"   ❌ Registration failed: {resp.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Step 4: List all agents
    print("\n4️⃣  Listing all registered agents...")
    try:
        resp = requests.get(f"{BASE_URL}/api/web/agents", timeout=5)
        if resp.status_code == 200:
            agents = resp.json()
            print(f"   ✅ Found {len(agents)} agent(s):")
            for agent in agents:
                print(f"      - {agent['agent_name']} (ID: {agent['agent_id']}, Status: {agent['status']})")
        else:
            print(f"   ❌ Failed to list agents: {resp.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Step 5: Trigger handshake
    print("\n5️⃣  Triggering handshakes...")
    for agent_id in [calc_id, gen_id]:
        try:
            resp = requests.get(f"{BASE_URL}/api/web/agents/{agent_id}/handshake", timeout=15)
            if resp.status_code == 200:
                status = resp.json().get('status', 'unknown')
                print(f"   ✅ Agent {agent_id}: Status = {status}")
            else:
                print(f"   ⚠️  Handshake response: {resp.status_code}")
        except Exception as e:
            print(f"   ⚠️  Handshake error for {agent_id}: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Test Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start test agent servers: python3 Agent/test_server.py")
    print("2. Open web console: http://127.0.0.1:5173")
    print("3. Check Agents page to see registered agents")
    return True

if __name__ == "__main__":
    success = test_agent_integration()
    sys.exit(0 if success else 1)
