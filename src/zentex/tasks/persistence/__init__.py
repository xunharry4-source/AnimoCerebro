"""Task Persistence subpackage - Handles task storage and data access."""

# Optional DAO imports (may fail if database not available)
try:
    from zentex.tasks.persistence.dao import (
        TaskDAO,
        SuspendedTaskDAO,
        TaskAuditLogDAO,
        InterventionReceiptDAO,
        IdempotencyLogDAO,
    )
    DAO_AVAILABLE = True
except ImportError:
    DAO_AVAILABLE = False
    TaskDAO = None
    SuspendedTaskDAO = None
    TaskAuditLogDAO = None
    InterventionReceiptDAO = None
    IdempotencyLogDAO = None

__all__ = [
    "TaskDAO",
    "SuspendedTaskDAO",
    "TaskAuditLogDAO",
    "InterventionReceiptDAO",
    "IdempotencyLogDAO",
]
