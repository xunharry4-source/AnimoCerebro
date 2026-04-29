from __future__ import annotations

"""Compatibility exports for task database access objects.

Historically callers imported DAO classes from ``zentex.tasks.dao``.
The concrete implementation now lives under ``zentex.tasks.persistence.dao``.
This module preserves the old import path so service initialization and tests
can enable the database layer again.
"""

from zentex.tasks.persistence import (
    DAO_AVAILABLE as DATABASE_AVAILABLE,
    IdempotencyLogDAO,
    InterventionReceiptDAO,
    SuspendedTaskDAO,
    TaskAuditLogDAO,
    TaskDAO,
    TaskOutcomeDAO,
)

__all__ = [
    "DATABASE_AVAILABLE",
    "TaskDAO",
    "SuspendedTaskDAO",
    "TaskAuditLogDAO",
    "TaskOutcomeDAO",
    "InterventionReceiptDAO",
    "IdempotencyLogDAO",
]
