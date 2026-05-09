from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

UTC = timezone.utc


class LeaseRecord(BaseModel):
    """Unified lease metadata shared by workers, schedulers, and guarded services."""

    status: str = "active"
    owner: str
    acquired_at: str
    heartbeat_at: str
    timeout_seconds: int = 30
    attempt_count: int = 0
    expired_at: Optional[str] = None
    released_at: Optional[str] = None
    extras: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(UTC)).isoformat()


def new_active_lease(
    *,
    owner: str,
    timeout_seconds: int = 30,
    attempt_count: int = 0,
    acquired_at: Optional[datetime] = None,
    extras: dict[str, Optional[Any]] = None,
) -> LeaseRecord:
    started = _iso(acquired_at)
    return LeaseRecord(
        status="active",
        owner=owner,
        acquired_at=started,
        heartbeat_at=started,
        timeout_seconds=int(timeout_seconds),
        attempt_count=int(attempt_count),
        extras=dict(extras or {}),
    )


def renew_lease_record(lease: Union[LeaseRecord, dict[str], Any], *, now: Optional[datetime] = None) -> LeaseRecord:
    current = LeaseRecord.model_validate(lease)
    return current.model_copy(update={"heartbeat_at": _iso(now), "status": "active"})


def expire_lease_record(lease: Union[LeaseRecord, dict[str], Any], *, now: Optional[datetime] = None) -> LeaseRecord:
    current = LeaseRecord.model_validate(lease)
    return current.model_copy(update={"status": "expired", "expired_at": _iso(now)})


def release_lease_record(lease: Union[LeaseRecord, dict[str], Any], *, now: Optional[datetime] = None) -> LeaseRecord:
    current = LeaseRecord.model_validate(lease)
    return current.model_copy(update={"status": "released", "released_at": _iso(now)})


def is_lease_expired(lease: Union[LeaseRecord, dict[str], Any], *, now: Optional[datetime] = None) -> bool:
    current = LeaseRecord.model_validate(lease)
    heartbeat_at = datetime.fromisoformat(current.heartbeat_at.replace("Z", "+00:00"))
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    return (reference - heartbeat_at).total_seconds() > current.timeout_seconds
