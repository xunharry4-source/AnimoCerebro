from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ExecutionMode(str, Enum):
    SIMULATE = "simulate"
    DRY_RUN = "dry_run"
    REAL = "real"


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: str = Field(min_length=1)
    target: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    requester_id: str = Field(default="zentex.runtime")
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    execution_mode: ExecutionMode = ExecutionMode.SIMULATE
    execution_domain: str = "ledger"
    protocol_id: str | None = None
    requires_cloud_audit: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str = Field(default_factory=lambda: str(uuid4()))
    action_id: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    status: Literal["simulated", "dry_run", "succeeded", "failed", "blocked", "cloud_audit_required"]
    execution_mode: ExecutionMode
    adapter_id: str | None = None
    protocol_id: str | None = None
    safety_decision_id: str | None = None
    safety_allowed: bool = False
    safety_status: str | None = None
    cloud_decision_status: str | None = None
    side_effect_committed: bool = False
    evidence_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
