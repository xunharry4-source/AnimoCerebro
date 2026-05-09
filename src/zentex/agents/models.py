from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

class AgentTrustLevel(str, Enum):
    PENDING = "pending"
    TRUSTED = "trusted"
    REVOKED = "revoked"

class AgentStatus(str, Enum):
    OFFLINE = "offline"
    HANDSHAKE_FAILED = "handshake_failed"
    AUDIT_FAILED = "audit_failed"
    INVOCATION_BLOCKED = "invocation_blocked"
    IDLE = "idle"
    BUSY = "busy"

class AgentAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, str_strip_whitespace=True)

    agent_id: str
    name: str
    agent_name: str
    version: str
    function_description: str
    endpoint: str
    auth_token: str
    role_tag: str
    trust_level: AgentTrustLevel
    status: AgentStatus
    scope: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    adapter_type: str = "legacy_bridge"
    adapter_config: Dict[str, Any] = Field(default_factory=dict)
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    service_hooks: List[str] = Field(default_factory=list)
    protocol_capabilities: List[str] = Field(default_factory=list)
    latency_ms: Optional[float] = None
    last_ping_at: Optional[datetime] = None

class AgentRegistrationRequest(BaseModel):
    name: str
    agent_name: str
    version: str
    function_description: str
    endpoint: str
    auth_token: str
    role_tag: str
    trust_level: AgentTrustLevel = AgentTrustLevel.PENDING
    scope: List[str] = Field(default_factory=list)
    adapter_type: str = "legacy_bridge"
    adapter_config: Dict[str, Any] = Field(default_factory=dict)
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    service_hooks: List[str] = Field(default_factory=list)
    protocol_capabilities: List[str] = Field(default_factory=list)
