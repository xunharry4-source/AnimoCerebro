from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional, Union

UTC = timezone.utc


class ResilienceStatus(StrEnum):
    """Unified execution and storage state vocabulary used across modules."""

    not_started = "not_started"
    ready = "ready"
    running = "running"
    completed = "completed"
    partial_failed = "partial_failed"
    failed = "failed"
    degraded = "degraded"
    skipped = "skipped"
    stale = "stale"
    missing = "missing"


class ResilienceErrorCode(StrEnum):
    """Stable machine-readable error codes shared across resilience paths."""

    STATE_CONFLICT = "state_conflict"
    EXECUTION_CONTRACT_VIOLATION = "execution_contract_violation"
    EXECUTION_ENTRYPOINT_MISSING = "execution_entrypoint_missing"
    SERVICE_ASSEMBLY_FAILED = "service_assembly_failed"
    STORAGE_NOT_COMMITTED = "storage_not_committed"
    STORAGE_COMMIT_INCOMPLETE = "storage_commit_incomplete"
    DATABASE_DEGRADED = "database_degraded"
    TASK_LEASE_EXPIRED = "task_lease_expired"


@dataclass(slots=True)
class ResilienceError:
    """Structured failure payload shared across service and storage boundaries."""

    code: str
    message: str
    retriable: bool = False
    degraded: bool = False
    source: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retriable": self.retriable,
            "degraded": self.degraded,
            "source": self.source,
            "details": dict(self.details),
        }


@dataclass(slots=True)
class OperationResult:
    """Unified result wrapper for resilience-sensitive operations."""

    status: str
    data: Any = None
    error: Optional[ResilienceError] = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source: str = ""

    @classmethod
    def success(
        cls,
        *,
        status: Union[ResilienceStatus, str] = ResilienceStatus.completed,
        data: Any = None,
        source: str = "",
    ) -> "OperationResult":
        return cls(status=str(status), data=data, source=source)

    @classmethod
    def failed(
        cls,
        *,
        status: Union[ResilienceStatus, str] = ResilienceStatus.failed,
        code: Union[ResilienceErrorCode, str],
        message: str,
        source: str = "",
        retriable: bool = False,
        degraded: bool = False,
        details: dict[str, Any] = None,
        data: Any = None,
    ) -> "OperationResult":
        return cls(
            status=str(status),
            data=data,
            source=source,
            error=ResilienceError(
                code=str(code),
                message=message,
                retriable=retriable,
                degraded=degraded,
                source=source,
                details=dict(details or {}),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        error_code = ""
        error_message = ""
        retriable = False
        degraded = False
        if self.error is not None:
            error_code = self.error.code
            error_message = self.error.message
            retriable = self.error.retriable
            degraded = self.error.degraded
        return {
            "status": self.status,
            "data": self.data,
            "error_code": error_code,
            "error_message": error_message,
            "retriable": retriable,
            "degraded": degraded,
            "error": self.error.to_dict() if self.error else None,
            "updated_at": self.updated_at,
            "source": self.source,
        }
