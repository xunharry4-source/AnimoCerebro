from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class SecurityBlockError(RuntimeError):
    """Raised when execution is blocked by mandatory safety or audit gates."""


class CloudAuditAuthError(SecurityBlockError):
    """Raised when a cloud-audited execution lacks a verified audit token."""


class ActionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    action_name: str = Field(min_length=1)
    action_payload: Dict[str, Any] = Field(default_factory=dict)
    risk_level: str = Field(min_length=1)
    requires_confirmation: bool = False


class ActionExecutionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ActionStatus
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_payload: Dict[str, Any] = Field(default_factory=dict)


class SafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    allowed: bool
    reason: str = Field(min_length=1)


class CloudAuditDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    verified: bool
    audit_token: Optional[str] = None
    reason: str = Field(min_length=1)


class ExecutionDomainPlugin(FunctionalPluginSpec, ABC):
    execution_domain: str = Field(min_length=1)
    requires_cloud_audit: bool
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN
    supports_multiple_plugins: bool = False

    @classmethod
    def plugin_kind(cls) -> str:
        return "execution_domain"

    @abstractmethod
    def execute_action(
        self,
        intent: ActionIntent,
        context: Dict[str, Any],
    ) -> ActionExecutionReceipt:
        """Execute a side-effecting action and return evidentiary receipt."""


class SafetyGate(ABC):
    @abstractmethod
    def check(
        self,
        intent: ActionIntent,
        context: Dict[str, Any],
        plugin: ExecutionDomainPlugin,
    ) -> SafetyDecision:
        """Return whether the action may proceed to execution."""


class CloudAuditClient(ABC):
    @abstractmethod
    def verify(
        self,
        intent: ActionIntent,
        context: Dict[str, Any],
        plugin: ExecutionDomainPlugin,
    ) -> CloudAuditDecision:
        """Verify cloud audit authorization for auditable execution domains."""
