from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from zentex.agents.manager import AgentStatus, AgentTrustLevel
from zentex.agents.verification import AgentVerificationPlan

# Re-exporting from core contracts
from zentex.agents.contracts import (
    AgentInboxItem,
    AgentReceiptItem,
    AgentStatusView as AgentConsoleRecord,  # Alias for backward compatibility
    AgentAuditRecord
)

class AgentRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)  # Technical ID
    agent_name: str = Field(min_length=1)  # Human readable name
    version: str = Field(min_length=1)
    function_description: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    auth_token: Optional[str] = None
    role_tag: str = Field(min_length=1)
    trust_level: AgentTrustLevel = AgentTrustLevel.PENDING
    scope: List[str] = Field(default_factory=list)
    adapter_type: str = "legacy_bridge"
    adapter_config: Dict[str, Any] = Field(default_factory=dict)
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    service_hooks: List[str] = Field(default_factory=list)
    protocol_capabilities: List[str] = Field(default_factory=list)

class AgentPolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_level: AgentTrustLevel
    scope: List[str]

class AgentHandshakeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    status: str
    capabilities: List[Dict[str, Any]]
    latency_ms: Optional[float] = None

class AgentCreditScoreDimension(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    score: float
    weight: float

class AgentCreditScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    total_score: float
    dimensions: List[AgentCreditScoreDimension]

class AgentStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    in_progress_tasks: int
    uptime_percentage: float

class AgentDispatchTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_payload: Dict[str, Any]
    zentex_task_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    verification_plan: Optional[AgentVerificationPlan] = None


class AgentCallbackResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    callback_token: Optional[str] = None
    status: str
    normalized_result: Any = None
    raw_response: Any = None


class AgentCredentialUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: Optional[str] = None
    credential_type: str = Field(min_length=1)
    secret_payload: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentAuthTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_refresh: bool = False
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    endpoint: Optional[str] = None
