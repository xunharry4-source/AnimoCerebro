from __future__ import annotations
"""Stable public exports for kernel models and helper facades.

This module is the only kernel-facing import surface intended for external
business modules during the runtime/core migration.
"""


from typing import Any, Optional

from zentex.kernel.cognition_flow.models import NineQuestionState
from zentex.kernel.cognition_flow.snapshot_builder import StartupSnapshotBuilder
from zentex.kernel.state_domain.brain_transcript import BrainTranscriptStore
from zentex.kernel.state_domain.brain_transcript_models import (
    BrainTranscriptEntry,
    BrainTranscriptEntryType,
)

AuditEventStore = BrainTranscriptStore
AuditEvent = BrainTranscriptEntry
AuditEventType = BrainTranscriptEntryType


def build_runtime_workspace_snapshot(bridge: Any, session_id: str) -> dict[str, Any]:
    """Build a startup snapshot through the stable kernel facade."""
    return StartupSnapshotBuilder(bridge).build(session_id)


def build_event(
    *,
    reason: str,
    trace_id: Optional[str] = None,
    source: str = "kernel.public",
    payload: dict[str, Optional[Any]] = None,
) -> dict[str, Any]:
    """Build a migration-safe nine-question event payload."""
    event: dict[str, Any] = {
        "reason": reason,
        "source": source,
    }
    if trace_id:
        event["trace_id"] = trace_id
    if payload:
        event["payload"] = dict(payload)
    return event


__all__ = [
    "AuditEvent",
    "AuditEventStore",
    "AuditEventType",
    "BrainTranscriptEntry",
    "BrainTranscriptEntryType",
    "BrainTranscriptStore",
    "NineQuestionState",
    "build_runtime_workspace_snapshot",
    "build_event",
]
