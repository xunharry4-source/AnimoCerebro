# Agent Management Module

## Overview
The Agent Management module handles the lifecycle of external and internal agents within the Zentex ecosystem. It provides secure registration, capability discovery (handshake), safety auditing, and task dispatching.

## Key Components

### 1. AgentManager (`zentex.agents.manager`)
- Acts as a registry for `AgentAsset` objects.
- Manages in-memory state of all known agents.
- Handles CRUD operations on agent assets.

### 2. AgentBridge (`zentex.agents.bridge`)
- Low-level network communication layer using `httpx`.
- Implements the standard protocol for:
  - `/handshake`: Capability discovery.
  - `/execute`: Task dispatch.
  - `/status`: Health monitoring.

### 3. AgentCoordinationService (`zentex.agents.service`)
- High-level orchestration and business logic.
- Enforces security redlines:
  - New agents start with `AgentTrustLevel.PENDING`.
  - Mandatory handshake and safety audit before promotion to `TRUSTED`.
- Maintains a permanent audit trail in the `BrainTranscriptStore`.
- Provides helper methods for UI (inbox, receipts, goals).

## Standard Protocol

Any agent wishing to integrate with Zentex MUST implement the following endpoints:

### POST `/handshake`
- **Request**: `Authorization: Bearer <token>`
- **Response**: 
  ```json
  {
    "agent_id": "string",
    "version": "string",
    "capabilities": [{"name": "string", "description": "string"}],
    "latency_ms": 12.5
  }
  ```

### POST `/execute`
- **Request**: `{"task_id": "...", "payload": {...}}`
- **Response**: `{"status": "success", "result": {...}}`

### GET `/status`
- **Response**: `200 OK` (if healthy)

## Usage Example

```python
from zentex.agents.manager import AgentManager
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest

# Initialize
manager = AgentManager()
service = AgentCoordinationService(manager, transcript_store)

# 1. Register
request = AgentRegistrationRequest(
    name="research-agent",
    agent_name="Research Pro",
    version="1.0.0",
    function_description="Searches for academic papers",
    endpoint="https://agent.example.com",
    auth_token="secure-token-123",
    role_tag="research"
)
asset = await service.register_agent(request)

# 2. Handshake (Discovery)
await service.perform_handshake(asset.agent_id)

# 3. Dispatch Task
result = await service.dispatch_task(asset.agent_id, {"query": "quantum computing"})
```
