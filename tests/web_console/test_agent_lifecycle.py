from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import sys
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Import the app and required models
from zentex.web_console.dev_server import app
from zentex.agents.manager import AgentStatus, AgentTrustLevel

@pytest.fixture
def client():
    return TestClient(app)

def test_agent_lifecycle_full_closed_loop(client: TestClient):
    # --- Task 1: Real Agent Registration & Handshake Assertions ---
    
    # 1. Register Random Number Agent (local mock: agent.random_number_agent)
    reg_payload_add = {
        "name": "random-number-agent-test",
        "agent_name": "Test Random Number Agent",
        "version": "1.0.0",
        "function_description": "Returns a random number for any input.",
        "endpoint": "http://127.0.0.1:9201",
        "auth_token": "test-token-123",
        "role_tag": "math-expert",
        "scope": ["math"]
    }
    response = client.post("/api/web/agents/register", json=reg_payload_add)
    assert response.status_code == 200
    agent_add = response.json()
    agent_add_id = agent_add["agent_id"]
    assert agent_add["registered_at"] is not None
    assert agent_add["trust_level"] == "pending" # Starts as pending

    # 2. Register Test Data Agent (local mock: agent.testdata_agent)
    reg_payload_data = {
        "name": "testdata-agent-test",
        "agent_name": "Test Data Agent",
        "version": "1.0.0",
        "function_description": "Generates test data files under testdata/.",
        "endpoint": "http://127.0.0.1:9202",
        "auth_token": "test-token-456",
        "role_tag": "data-provider",
        "scope": ["data"]
    }
    response = client.post("/api/web/agents/register", json=reg_payload_data)
    assert response.status_code == 200
    agent_data = response.json()
    agent_data_id = agent_data["agent_id"]

    # 3. Perform Handshake for Random Number Agent
    handshake_payload_add = {
        "capabilities": [{"capability": "random_number", "version": "1.0.0"}]
    }
    response = client.post(f"/api/web/agents/{agent_add_id}/handshake", json=handshake_payload_add)
    assert response.status_code == 200
    updated_add = response.json()
    assert updated_add["capabilities"][0]["capability"] == "random_number"
    assert updated_add["trust_level"] == "trusted" # Mock auto-promotion passed

    # 4. Perform Handshake for Test Data Agent
    handshake_payload_data = {
        "capabilities": [{"capability": "testdata_generation", "version": "1.0.0"}]
    }
    response = client.post(f"/api/web/agents/{agent_data_id}/handshake", json=handshake_payload_data)
    assert response.status_code == 200
    updated_data = response.json()
    # Check differentiation
    assert updated_data["capabilities"][0]["capability"] == "testdata_generation"
    assert updated_data["capabilities"][0]["capability"] != updated_add["capabilities"][0]["capability"]

    # --- Task 2: Status Deactivation & Blockage Assertions ---

    # 1. Deactivate Random Number Agent (Policy Update)
    policy_payload = {
        "trust_level": "revoked",
        "scope": []
    }
    response = client.patch(f"/api/web/agents/{agent_add_id}/policy", json=policy_payload)
    assert response.status_code == 200
    assert response.json()["trust_level"] == "revoked"

    # 2. Verify status via list
    response = client.get("/api/web/agents")
    agents = response.json()
    target_agent = next(a for a in agents if a["agent_id"] == agent_add_id)
    assert target_agent["trust_level"] == "revoked"

    # [ABSOLUTE BLOCKAGE REDLINE]: Test the thinking bridge blockage
    # Calls service.think_about_task(agent_add_id, ...)
    think_payload = {"context": {"task": "calculate 2+2"}}
    response = client.post(f"/api/web/agents/{agent_add_id}/think-task", json=think_payload)
    assert response.status_code == 200
    # Must be BLOCKED_BY_BOUNDARY because trust_level is revoked
    assert response.json()["decision"] == "blocked_by_boundary"

    # --- Task 3: Agent physical/logical deletion clearnup assertions ---

    # 1. Delete Test Data Agent
    response = client.delete(f"/api/web/agents/{agent_data_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    # 2. Assert disappearance from list
    response = client.get("/api/web/agents")
    agents_after = response.json()
    assert not any(a["agent_id"] == agent_data_id for a in agents_after)

    # 3. Assert NineQuestionState Q3 scan exclusion (Simulated)
    # Since Q3 pulls from manager.list_assets(), and agent_data is deleted,
    # any new Q3 scan will not see it.
    runtime = app.state.runtime
    # In a real ThinkLoop turn, Q3 would look like this:
    connected_agents = [a for a in runtime.agent_manager.list_assets()]
    assert not any(a.agent_id == agent_data_id for a in connected_agents)
