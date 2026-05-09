"""
Kernel module — pure turn execution and state management layer for zentex.

RESPONSIBILITY:
This module executes turns (9-phase cognition cycle), manages session lifecycle,
maintains state across turns, and provides state query APIs. It is the "business logic"
engine, orchestrating external services (plugins, memory, cognition, etc.) to drive
the reasoning cycle.

PROVIDES:
- Session lifecycle management (create, suspend, terminate)
- Turn execution (9-phase protocol: observe → perceive → recognize → reason → decide
  → plan → prepare → act → consolidate)
- Session state queries (working memory, audit log, session meta, audit events)
- Nine-question bootstrap and Q1-Q9 cognitive plugin coordination
- Bridge to external services (environment, cognition, memory, safety, plugins, llm)

DOES NOT:
- Define protocols or system capabilities (foundation's responsibility)
- Start the system or wire services together (launcher's responsibility)
- Implement reasoning logic itself (delegated to cognition.service)
- Call other modules' internals directly (only via injected service dependencies)
- Expose any __runtime, __core, __boot internal modules or files

ARCHITECTURE:
- KernelService: public entry point (service-only boundary)
- session_domain: session registry and lifecycle
- state_domain: working memory, self-model, temporal state, audit events
- cognition_flow: 9-phase turn execution engine (router, executor, models)
- flow_domain: phase definitions and turn protocol

PUBLIC API:
Only import KernelService and get_service() from this module.
All other submodules are internal to kernel and should not be imported by external code.
"""

from zentex.kernel.service import KernelService, get_service
from zentex.kernel.public import (
    AuditEvent,
    AuditEventStore,
    AuditEventType,
    BrainTranscriptEntry,
    BrainTranscriptEntryType,
    BrainTranscriptStore,
    NineQuestionState,
    build_event,
    build_runtime_workspace_snapshot,
)

__all__ = [
    "KernelService",
    "get_service",
    "AuditEvent",
    "AuditEventStore",
    "AuditEventType",
    "BrainTranscriptEntry",
    "BrainTranscriptEntryType",
    "BrainTranscriptStore",
    "NineQuestionState",
    "build_event",
    "build_runtime_workspace_snapshot",
]
