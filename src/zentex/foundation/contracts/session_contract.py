"""Session lifecycle contracts — metadata and snapshot models."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import Field

from zentex.foundation.contracts.base_models import ZentexBaseModel

UTC = timezone.utc


class SessionStatus(StrEnum):
    active = "active"
    idle = "idle"
    suspended = "suspended"
    terminated = "terminated"


class SessionMeta(ZentexBaseModel):
    """Core metadata for an active or historical session."""

    session_id: str
    user_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: SessionStatus = SessionStatus.active


class SessionSnapshot(ZentexBaseModel):
    """Point-in-time snapshot of session state for persistence or handoff."""

    meta: SessionMeta
    working_memory_slots: list[dict] = Field(default_factory=list)
    nine_question_state: dict = Field(default_factory=dict)
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
