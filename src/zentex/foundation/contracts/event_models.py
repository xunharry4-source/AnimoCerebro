"""Event types and envelope models for the Zentex event bus."""

from enum import StrEnum
from uuid import uuid4

from pydantic import Field

from zentex.foundation.contracts.base_models import AuditableModel, ZentexBaseModel


class ZentexEventType(StrEnum):
    turn_start = "turn_start"
    turn_end = "turn_end"
    phase_start = "phase_start"
    phase_end = "phase_end"
    bootstrap_start = "bootstrap_start"
    bootstrap_end = "bootstrap_end"
    session_created = "session_created"
    session_terminated = "session_terminated"
    plugin_registered = "plugin_registered"
    plugin_disabled = "plugin_disabled"
    error = "error"
    audit = "audit"


class ZentexEvent(AuditableModel):
    """A structured system event."""

    event_type: ZentexEventType
    session_id: str = ""
    turn_id: str = ""
    payload: dict = Field(default_factory=dict)


class EventEnvelope(ZentexBaseModel):
    """Transport wrapper around a ZentexEvent."""

    event: ZentexEvent
    envelope_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "1.0"
