from __future__ import annotations
from typing import Optional


"""
Unified runtime lifecycle contracts for Zentex plugins.

This module builds on `BasePluginSpec` and defines the normalized runtime
records required to operate plugins safely inside Zentex:

- health probing
- load and switch outcomes
- rollback decisions
- revocation records

The goal is to ensure every plugin family speaks the same operational language
for degrade, isolation, rollback, and audit.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus


class PluginLoadAction(str, Enum):
    LOADED = "loaded"
    SWITCHED = "switched"
    DEGRADED = "degraded"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"
    REVOKED = "revoked"


class PluginDegradeState(str, Enum):
    NONE = "none"
    DEGRADED = "degraded"
    ISOLATED = "isolated"


class PluginHealthProbeResult(BaseModel):
    """Normalized runtime result of a plugin health probe."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    plugin_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    health_status: PluginHealthStatus
    checked_at: datetime
    latency_ms: float = Field(ge=0)
    timed_out: bool = False
    error_message: Optional[str] = None

    @model_validator(mode="after")
    def validate_timeout_and_error_contract(self) -> "PluginHealthProbeResult":
        if self.timed_out and not self.error_message:
            raise ValueError("Timed-out health probes must preserve an error_message.")
        if self.health_status == PluginHealthStatus.UNHEALTHY and not self.error_message:
            raise ValueError("Unhealthy probes must preserve an error_message.")
        return self


class PluginRollbackDecision(BaseModel):
    """Decision record describing when and where plugin runtime must roll back."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    plugin_id: str = Field(min_length=1)
    from_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    trigger_condition: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    decided_at: datetime
    isolated: bool
    transcript_write_required: bool = True


class PluginRevocationRecord(BaseModel):
    """Auditable record describing plugin rejection or revocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    plugin_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    revocation_condition: str = Field(min_length=1)
    recorded_at: datetime
    transcript_write_required: bool = True


class PluginLoadResult(BaseModel):
    """
    Normalized runtime outcome for plugin load, switch, degrade, or rollback.

    Defense rules:
    - degrade, reject, revoke, and rollback outcomes must preserve audit reasons
    - rollback outcomes must point to a target audited version
    - degraded or isolated outcomes must carry health evidence or error detail
    """

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    plugin_id: str = Field(min_length=1)
    requested_version: str = Field(min_length=1)
    effective_version: str = Field(min_length=1)
    status: PluginLifecycleStatus
    action: PluginLoadAction
    degrade_state: PluginDegradeState = PluginDegradeState.NONE
    loaded_at: datetime
    health_probe: Optional[PluginHealthProbeResult] = None
    audit_reason: Optional[str] = None
    error_message: Optional[str] = None
    rollback_target_version: Optional[str] = None
    revocation_record: Optional[PluginRevocationRecord] = None
    rollback_decision: Optional[PluginRollbackDecision] = None

    @model_validator(mode="after")
    def validate_outcome_contract(self) -> "PluginLoadResult":
        audit_actions = {
            PluginLoadAction.DEGRADED,
            PluginLoadAction.ROLLED_BACK,
            PluginLoadAction.REJECTED,
            PluginLoadAction.REVOKED,
        }
        if self.action in audit_actions and not self.audit_reason:
            raise ValueError("Audit reason is required for degraded, rollback, rejected, or revoked plugin outcomes.")

        if self.action == PluginLoadAction.ROLLED_BACK:
            if not self.rollback_target_version:
                raise ValueError("Rolled-back plugin outcomes must declare rollback_target_version.")
            if self.rollback_decision is None:
                raise ValueError("Rolled-back plugin outcomes must preserve rollback_decision.")

        if self.action == PluginLoadAction.REVOKED and self.revocation_record is None:
            raise ValueError("Revoked plugin outcomes must preserve revocation_record.")

        degraded_state = self.degrade_state != PluginDegradeState.NONE
        degraded_status = self.status in {
            PluginLifecycleStatus.DEGRADED,
            PluginLifecycleStatus.REVOKED,
        }
        if degraded_state or degraded_status:
            if self.health_probe is None and not self.error_message:
                raise ValueError(
                    "Degraded or isolated plugin outcomes must preserve health_probe or error_message."
                )

        return self
