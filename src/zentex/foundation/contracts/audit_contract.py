"""Audit contracts — entries, trails and decisions."""

from uuid import uuid4

from pydantic import Field

from zentex.foundation.contracts.base_models import AuditableModel, ZentexBaseModel


class AuditEntry(AuditableModel):
    """A single immutable audit record."""

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    target_id: str = ""
    target_type: str = ""
    result: str = ""
    metadata: dict = Field(default_factory=dict)


class AuditTrail(ZentexBaseModel):
    """An ordered, immutable sequence of AuditEntry records for a session."""

    trail_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    entries: list[AuditEntry] = Field(default_factory=list)

    def append(self, entry: AuditEntry) -> "AuditTrail":
        """Return a new AuditTrail with *entry* appended (immutable update)."""
        return self.model_copy(update={"entries": [*self.entries, entry]})


class AuditDecision(ZentexBaseModel):
    """The outcome of an audit evaluation."""

    passed: bool
    reason: str = ""
    responsible_module: str = ""
    confidence: float = 1.0
