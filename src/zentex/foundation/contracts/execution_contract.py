"""Execution action contracts — intent, result and safety decision models."""

from enum import Enum

from pydantic import Field

from zentex.foundation.contracts.base_models import ZentexBaseModel


class ActionStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class ActionIntent(ZentexBaseModel):
    """Describes what action is being requested."""

    action_type: str
    target: str = ""
    parameters: dict = Field(default_factory=dict)
    requester_id: str = ""


class ActionResult(ZentexBaseModel):
    """The outcome of executing an ActionIntent."""

    intent: ActionIntent
    status: ActionStatus
    output: dict = Field(default_factory=dict)
    duration_ms: float = 0.0
    audit_id: str = ""


class SafetyDecision(ZentexBaseModel):
    """Result of a safety policy evaluation for a proposed action."""

    allowed: bool
    reason: str = ""
    confidence: float = 1.0
    blocking_rule: str = ""
