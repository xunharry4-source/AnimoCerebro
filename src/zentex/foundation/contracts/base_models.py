"""Base Pydantic models shared across all contract definitions."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

UTC = timezone.utc


class ZentexBaseModel(BaseModel):
    """Root base model: frozen, no extra fields allowed."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TimestampedModel(ZentexBaseModel):
    """Adds creation and last-update timestamps."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditableModel(TimestampedModel):
    """Adds audit metadata on top of timestamps."""

    source_module: str = ""
    operator_id: str = ""
    operation_type: str = ""
