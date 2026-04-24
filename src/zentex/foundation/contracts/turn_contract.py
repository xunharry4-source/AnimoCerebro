"""Turn lifecycle contracts — request, phase results and turn result models."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import Field

from zentex.foundation.contracts.base_models import ZentexBaseModel

UTC = timezone.utc


class TurnStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    partial_failed = "partial_failed"
    failed = "failed"
    aborted = "aborted"


class PhaseResult(ZentexBaseModel):
    """Outcome of a single processing phase within a turn."""

    phase_name: str
    output: dict = Field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""
    skipped: bool = False


class TurnRequest(ZentexBaseModel):
    """Incoming user turn to be processed by the system."""

    turn_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    user_input: str
    context: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TurnResult(ZentexBaseModel):
    """Final result produced by the system for a user turn."""

    turn_id: str
    session_id: str
    status: TurnStatus
    response: str = ""
    phase_results: list[PhaseResult] = Field(default_factory=list)
    audit_trail_id: str = ""
    duration_ms: float = 0.0
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
