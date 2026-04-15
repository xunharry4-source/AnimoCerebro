"""Identity contract types: version, lock, and core identity model."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import Field

from zentex.foundation.contracts import ZentexBaseModel

UTC = timezone.utc


class IdentityVersion(ZentexBaseModel):
    """Tracks the version of an identity snapshot."""

    version_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime
    description: str = ""


class IdentityLock(ZentexBaseModel):
    """Declares which identity fields are immutable and why."""

    locked_fields: frozenset[str] = frozenset()
    lock_reason: str = ""

    def is_locked(self, field: str) -> bool:
        """Return True if the named field is protected by this lock."""
        return field in self.locked_fields


class IdentityCore(ZentexBaseModel):
    """The immutable core identity of a Zentex agent."""

    role_name: str
    mission: str
    core_values: tuple[str, ...]
    continuity_lock: IdentityLock = Field(
        default_factory=lambda: IdentityLock(
            locked_fields=frozenset(["role_name", "mission", "core_values"])
        )
    )
    version: IdentityVersion = Field(
        default_factory=lambda: IdentityVersion(created_at=datetime.now(UTC))
    )

    def is_field_locked(self, field: str) -> bool:
        """Return True if the named field is protected by the continuity lock."""
        return self.continuity_lock.is_locked(field)
