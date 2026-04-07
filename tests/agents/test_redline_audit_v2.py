import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from zentex.agents.manager import AgentManager, AgentStatus, AgentTrustLevel
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest
from pydantic import ValidationError

async def test_agent_registration_redline_v2():
    print("Running Agent Registration Redline V2 (Mandatory Fields) Test...")
    
    transcript_store = Mock()
    manager = AgentManager()
    service = AgentCoordinationService(manager, transcript_store)
    
    # 1. Test Fail-Closed: Missing mandatory fields
    print("Step 1: Testing missing mandatory fields (Expect ValidationError/422)...")
    try:
        # Missing agent_name, version, function_description
        AgentRegistrationRequest(
            name="test-id",
            endpoint="http://test.io",
            auth_token="tok",
            role_tag="worker"
        )
        assert False, "ERROR: Pydantic failed to catch missing mandatory fields!"
    except ValidationError as exc:
        print(f"PASS: Caught expected validation error: {len(exc.errors())} missing fields.")

    # 2. Test Success: Full Profile
    print("\nStep 2: Testing full profile registration...")
    request = AgentRegistrationRequest(
        name="defense-01",
        agent_name="Zentex Defense Sentry",
        version="2.1.0",
        function_description="Performs real-time cloud audit and security gatekeeping.",
        endpoint="https://safe.zentex.io",
        auth_token="secure-token",
        role_tag="defense"
    )
    
    asset = await service.register_agent(request)
    assert asset.agent_name == "Zentex Defense Sentry"
    assert asset.version == "2.1.0"
    assert asset.trust_level == AgentTrustLevel.PENDING
    print(f"PASS: Agent {asset.agent_name} registered in PENDING state with version {asset.version}")

    # 3. Test Task Monitoring Unified Model
    print("\nStep 3: Testing Task Unified Model retrieval...")
    tasks = await service.get_agent_tasks(asset.agent_id)
    assert len(tasks) > 0
    mandatory_fields = [
        "task_id", "subtask_id", "title", "task_type", "status", 
        "progress", "originator_id", "remarks", "started_at", "completed_at"
    ]
    for task in tasks:
        for field in mandatory_fields:
            assert field in task, f"ERROR: Task missing mandatory field: {field}"
    
    print("PASS: All 10 mandatory task fields are present in the response.")
    print("\nALL V2 UPGRADE REDLINE TESTS PASSED.")

if __name__ == "__main__":
    asyncio.run(test_agent_registration_redline_v2())
