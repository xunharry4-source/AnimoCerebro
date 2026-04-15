"""Sensory signal models — raw ingestion, sanitisation and environment events."""

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import Field

from zentex.foundation.contracts.base_models import AuditableModel, ZentexBaseModel

UTC = timezone.utc


class SignalSecurityTag(StrEnum):
    clean = "clean"
    sanitized = "sanitized"
    quarantined = "quarantined"
    unknown = "unknown"


class RawSignal(ZentexBaseModel):
    """An unprocessed signal received from an environment adapter."""

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict = Field(default_factory=dict)


class SanitizedSignal(ZentexBaseModel):
    """A signal that has been through the sensory sanitisation pipeline."""

    raw_signal_id: str
    source: str
    timestamp: datetime
    payload: dict = Field(default_factory=dict)
    security_tag: SignalSecurityTag = SignalSecurityTag.unknown
    sanitization_notes: str = ""


class EnvironmentEvent(AuditableModel):
    """A semantic event derived from one or more sanitised signals."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_kind: str
    data: dict = Field(default_factory=dict)
    signal_id: str = ""
