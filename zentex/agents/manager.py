from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from zentex.tasks.service import ZentexTask


class AgentTrustLevel(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    TRUSTED = "trusted"
    RESTRICTED = "restricted"
    REVOKED = "revoked"


class AgentStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    OFFLINE = "offline"
    HANDSHAKE_FAILED = "handshake_failed"
    AUDIT_FAILED = "audit_failed"


class AgentAsset(BaseModel):
    agent_id: str
    name: str # The unique technical ID
    agent_name: str # The human-readable name
    version: str
    function_description: str
    endpoint: str
    auth_token: Optional[str] = Field(default=None, exclude=True)
    role_tag: str
    trust_level: AgentTrustLevel = AgentTrustLevel.PENDING
    status: AgentStatus = AgentStatus.OFFLINE
    scope: List[str] = Field(default_factory=list)
    capabilities: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms: Optional[float] = None
    success_rate: float = 1.0
    last_ping_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))





class AgentManager:
    """
    Agent Asset Management Center.
    Handles registration, discovery, and high-level status of agent as assets.
    """
    
    def __init__(self) -> None:
        self._assets: Dict[str, AgentAsset] = {}

    def add_asset(self, asset: AgentAsset) -> None:
        self._assets[asset.agent_id] = asset

    def get_asset(self, agent_id: str) -> Optional[AgentAsset]:
        return self._assets.get(agent_id)

    def list_assets(self) -> List[AgentAsset]:
        return list(self._assets.values())

    def update_asset(self, agent_id: str, **kwargs: Any) -> Optional[AgentAsset]:
        asset = self._assets.get(agent_id)
        if asset:
            # Pydantic v2: model_dump() with exclude=True for some fields will cause validation error
            # when re-creating from the dict if those fields are required.
            # However, auth_token is Optional, so that might not be it.
            # Let's use model_copy with update instead.
            new_asset = asset.model_copy(update=kwargs)
            self._assets[agent_id] = new_asset
            return new_asset
        return None

    def remove_asset(self, agent_id: str) -> bool:
        if agent_id in self._assets:
            del self._assets[agent_id]
            return True
        return False

    def clear_assets(self) -> None:
        self._assets.clear()
