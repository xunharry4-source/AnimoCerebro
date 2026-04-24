from __future__ import annotations
"""
Unified service response structure for all cross-module service calls.

Every service API in the new architecture returns a ServiceResponse (or a
subclass).  This ensures status, error codes, audit refs, and trace IDs are
always present and structurally consistent across foundation / kernel /
launcher and all external modules.
"""


from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Status & error-code enumerations
# ---------------------------------------------------------------------------


class ServiceStatus(str, Enum):
    """Top-level outcome status of a service call."""

    ok = "ok"
    error = "error"
    timeout = "timeout"
    unavailable = "unavailable"
    partial = "partial"          # partial success (some sub-operations failed)


class ServiceErrorCode(str, Enum):
    """Stable, machine-readable error codes.

    Calling code may switch on these codes without parsing error messages.
    New codes must be added here before being returned by any service.
    """

    # Caller-side errors
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PERMISSION_DENIED = "PERMISSION_DENIED"

    # Runtime / dependency errors
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    SERVICE_TIMEOUT = "SERVICE_TIMEOUT"
    STATE_CONFLICT = "STATE_CONFLICT"

    # Governance errors
    AUDIT_REQUIRED = "AUDIT_REQUIRED"

    # Unrecoverable internal errors
    INTERNAL_UNRECOVERABLE = "INTERNAL_UNRECOVERABLE"


# ---------------------------------------------------------------------------
# ServiceCallContext — audit fields attached to every outgoing call
# ---------------------------------------------------------------------------


@dataclass
class ServiceCallContext:
    """Audit metadata that every cross-module service call must carry.

    Callers construct this and pass it alongside the business payload.
    Services must persist the trace_id into their audit trail.
    """

    caller_module: str
    caller_service: str
    operation: str

    # Auto-generated if not supplied
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    requested_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    # Optional context identifiers
    session_id: str = ""
    turn_id: str = ""
    decision_id: str = ""
    originator_id: str = ""
    target_module: str = ""
    target_service: str = ""


# ---------------------------------------------------------------------------
# ServiceResponse — unified return wrapper
# ---------------------------------------------------------------------------


@dataclass
class ServiceResponse:
    """Standard response envelope returned by every service API.

    Conventions
    -----------
    - ``status`` is always set.
    - ``code`` is set to a ``ServiceErrorCode`` value when ``status != ok``.
    - ``data`` holds the operation-specific result object (may be None).
    - ``trace_id`` must match the ``ServiceCallContext.trace_id`` of the
      originating call so callers can correlate request ↔ response.
    - ``audit_ref`` is the transcript / audit-trail entry ID written by the
      service during this call.

    For flow-type APIs (start_turn, ensure_bootstrap, etc.) the timing fields
    ``started_at``, ``finished_at``, ``elapsed_ms``, and ``stage`` should also
    be populated.
    """

    status: ServiceStatus
    data: Any = None

    # Error information (populated when status != ok)
    code: str = ""
    message: str = ""

    # Correlation
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    audit_ref: str = ""

    # Timing — populated by flow-type APIs
    started_at: str = ""
    finished_at: str = ""
    elapsed_ms: float = 0.0
    stage: str = ""

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def ok(
        cls,
        data: Any = None,
        trace_id: str = "",
        audit_ref: str = "",
        **timing: Any,
    ) -> "ServiceResponse":
        """Create a successful response."""
        return cls(
            status=ServiceStatus.ok,
            data=data,
            trace_id=trace_id or str(uuid4()),
            audit_ref=audit_ref,
            **timing,
        )

    @classmethod
    def error(
        cls,
        code: Union[ServiceErrorCode, str],
        message: str,
        trace_id: str = "",
        audit_ref: str = "",
        data: Any = None,
    ) -> "ServiceResponse":
        """Create an error response."""
        code_str = code.value if hasattr(code, "value") else str(code)
        return cls(
            status=ServiceStatus.error,
            code=code_str,
            message=message,
            data=data,
            trace_id=trace_id or str(uuid4()),
            audit_ref=audit_ref,
        )

    @classmethod
    def timeout(
        cls,
        message: str = "Operation timed out",
        trace_id: str = "",
    ) -> "ServiceResponse":
        """Create a timeout response."""
        return cls(
            status=ServiceStatus.timeout,
            code=ServiceErrorCode.SERVICE_TIMEOUT.value,
            message=message,
            trace_id=trace_id or str(uuid4()),
        )
    @classmethod
    def unavailable(
        cls,
        service_name: str = "",
        trace_id: str = "",
    ) -> "ServiceResponse":
        """Create a dependency-unavailable response."""
        msg = (
            f"Service '{service_name}' is unavailable"
            if service_name
            else "Required dependency is unavailable"
        )
        return cls(
            status=ServiceStatus.unavailable,
            code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE.value,
            message=msg,
            trace_id=trace_id or str(uuid4()),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_ok(self) -> bool:
        return self.status == ServiceStatus.ok

    @property
    def is_error(self) -> bool:
        return self.status in (
            ServiceStatus.error,
            ServiceStatus.timeout,
            ServiceStatus.unavailable,
        )

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "data": self.data,
            "trace_id": self.trace_id,
            "audit_ref": self.audit_ref,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": self.elapsed_ms,
            "stage": self.stage,
        }
