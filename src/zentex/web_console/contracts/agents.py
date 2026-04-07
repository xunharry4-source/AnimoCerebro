from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.agents.manager import AgentStatus, AgentTrustLevel


class AgentPolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trust_level: AgentTrustLevel
    scope: List[str]


class AgentDispatchTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_payload: Dict[str, Any]


class AgentInboxItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    title: str
    status: str
    idempotency_key: str
    originator_id: str
    remarks: Optional[str] = None


class AgentReceiptItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    title: str
    status: str
    idempotency_key: str
    completed_at: Optional[str] = None
    remarks: Optional[str] = None


class AgentConsoleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    name: str
    agent_name: str
    version: str
    function_description: str
    endpoint: str
    role_tag: str
    trust_level: AgentTrustLevel
    status: AgentStatus
    scope: List[str] = Field(default_factory=list)
    capabilities: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms: Optional[float] = None
    success_rate: float
    last_ping_at: Optional[str] = None
    registered_at: str
    inbox: List[AgentInboxItem] = Field(default_factory=list)
    assigned_goal: Optional[str] = None
    receipts: List[AgentReceiptItem] = Field(default_factory=list)


class AgentAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    event_type: str
    timestamp: str
    summary: str
    details: Dict[str, Any]
