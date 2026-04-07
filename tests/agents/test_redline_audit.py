import asyncio
import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from zentex.agents.manager import AgentManager, AgentStatus, AgentTrustLevel
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest
from unittest.mock import Mock

async def test_agent_registration_redline():
    print("Running Agent Registration Redline Test...")
    
    # 1. Setup
    transcript_store = Mock()
    manager = AgentManager()
    service = AgentCoordinationService(manager, transcript_store)
    
    # 2. Register an agent
    request = AgentRegistrationRequest(
        name="Test Defense Agent",
        endpoint="https://malicious.example.com", # Contains 'malicious', should trigger audit failure in my mock logic
        auth_token="secret-token",
        role_tag="defense"
    )
    
    print(f"Step 1: Registering agent with endpoint: {request.endpoint}")
    asset = await service.register_agent(request)
    
    # Assert initial state is PENDING
    assert asset.trust_level == AgentTrustLevel.PENDING, "ERROR: Agent did not start as PENDING!"
    print(f"PASS: Initial trust level is {asset.trust_level}")
    
    # 3. Simulate automatic handshake and safety audit
    print("Step 2: Performing handshake and safety audit...")
    await service.perform_handshake(asset.agent_id)
    
    # Check if logic correctly blocked promotion due to 'malicious' in endpoint
    updated_asset = manager.get_asset(asset.agent_id)
    assert updated_asset.trust_level == AgentTrustLevel.REVOKED, f"ERROR: Malicious agent promoted! Level: {updated_asset.trust_level}"
    assert updated_asset.status == AgentStatus.AUDIT_FAILED, "ERROR: Status not set to AUDIT_FAILED!"
    
    print("PASS: Malicious agent correctly blocked and REVOKED.")
    
    # 4. Success case
    request_safe = AgentRegistrationRequest(
        name="Safe Agent",
        endpoint="https://safe-node.zentex.io",
        auth_token="safe-token",
        role_tag="worker"
    )
    print(f"\nStep 3: Registering safe agent: {request_safe.name}")
    asset_safe = await service.register_agent(request_safe)
    await service.perform_handshake(asset_safe.agent_id)
    
    updated_safe = manager.get_asset(asset_safe.agent_id)
    assert updated_safe.trust_level == AgentTrustLevel.TRUSTED, "ERROR: Safe agent not trusted!"
    print(f"PASS: Safe agent correctly promoted to {updated_safe.trust_level}")
    
    print("\nALL DEFENSE REDLINE TESTS PASSED.")

if __name__ == "__main__":
    asyncio.run(test_agent_registration_redline())
