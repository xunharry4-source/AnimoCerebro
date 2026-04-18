"""
Memory Service Builders — payload construction helpers for web_console memory routes.

RESPONSIBILITY:
  Pure functions that transform EnhancedMemoryService data into typed web-console
  payload objects (overview, record list, search results, audit trail).
  Does NOT own any state, routes, or session management.

CAPABILITIES:
  - build_enhanced_memory_overview()        — aggregate statistics across layers
  - build_enhanced_memory_records_payload() — filtered/paginated record list
  - build_enhanced_memory_search_payload()  — semantic search results
  - build_enhanced_memory_audit_payload()   — audit trail for a single record
  - build_enhanced_memory_record_item()     — single-record detail
  - build_recall_hit_item()                 — recall hit detail
  - build_memory_audit_event_item()         — audit event detail

PARAMETER NOTE (lifecycle_status):
  build_enhanced_memory_records_payload() accepts `lifecycle_status` (not `status`)
  to match both the caller in memory_commons.py and the underlying
  service.list_managed_records(lifecycle_status=...) kwarg.

DOES NOT:
  - Define routes (routes live in the memory router module).
  - Mutate memory records.
  - Fall back to synthetic empty payloads on service failure — callers own that.
"""

from __future__ import annotations

from typing import Any, Protocol

from zentex.web_console.contracts.memory import (
    EnhancedMemoryAuditEventItem,
    EnhancedMemoryAuditPayload,
    EnhancedMemoryOverviewPayload,
    EnhancedMemoryRecordItem,
    EnhancedMemoryRecallHitItem,
    EnhancedMemoryRecordsPayload,
    EnhancedMemorySearchPayload,
    MemoryBackendStatusItem,
)


class _ModelDumpLike(Protocol):
    def model_dump(self) -> dict[str, Any]: ...


class _EnhancedMemoryServiceLike(Protocol):
    def list_managed_records(self, *args: Any, **kwargs: Any) -> list[Any]: ...

    def list_semantic_records(self) -> list[Any]: ...

    def list_procedural_records(self) -> list[Any]: ...

    def list_episodic_records(self) -> list[Any]: ...

    def list_projection_failures(self) -> list[Any]: ...

    def get_backend_status(self) -> list[Any]: ...

    def recall(self, *args: Any, **kwargs: Any) -> list[Any]: ...

    def list_audit_events(self, *args: Any, **kwargs: Any) -> list[Any]: ...


def build_enhanced_memory_record_item(record: _ModelDumpLike) -> EnhancedMemoryRecordItem:
    return EnhancedMemoryRecordItem.model_validate(record.model_dump())


def build_recall_hit_item(hit: _ModelDumpLike) -> EnhancedMemoryRecallHitItem:
    return EnhancedMemoryRecallHitItem.model_validate(hit.model_dump())


def build_memory_audit_event_item(event: _ModelDumpLike) -> EnhancedMemoryAuditEventItem:
    """Convert MemoryAuditEvent to EnhancedMemoryAuditEventItem.
    
    Handles datetime to string conversion for created_at field.
    """
    event_dict = event.model_dump()
    # Convert datetime to ISO format string if present
    if 'created_at' in event_dict and event_dict['created_at'] is not None:
        from datetime import datetime
        if isinstance(event_dict['created_at'], datetime):
            event_dict['created_at'] = event_dict['created_at'].isoformat()
    return EnhancedMemoryAuditEventItem.model_validate(event_dict)


def build_enhanced_memory_overview(
    service: _EnhancedMemoryServiceLike,
) -> EnhancedMemoryOverviewPayload:
    managed = service.list_managed_records(limit=10000)
    return EnhancedMemoryOverviewPayload(
        semantic_count=len(service.list_semantic_records()),
        procedural_count=len(service.list_procedural_records()),
        episodic_count=len(service.list_episodic_records()),
        active_count=sum(1 for item in managed if item.status == "active"),
        deprecated_count=sum(1 for item in managed if item.status == "deprecated"),
        archived_count=sum(1 for item in managed if item.status == "archived"),
        suspect_count=sum(1 for item in managed if item.trust_level == "suspect"),
        projection_failures=service.list_projection_failures(),
        backends=[
            MemoryBackendStatusItem.model_validate(item.model_dump())
            for item in service.get_backend_status()
        ],
    )


def build_enhanced_memory_records_payload(
    service: _EnhancedMemoryServiceLike,
    *,
    layer: str,
    limit: int,
    lifecycle_status: str | None,
    visibility: str | None,
    trust_level: str | None,
    trace_id: str | None,
    target_id: str | None,
    tag: str | None,
) -> EnhancedMemoryRecordsPayload:
    normalized = layer.lower()
    records = service.list_managed_records(
        layer=normalized,
        limit=limit,
        status=lifecycle_status,  # FIX: Use 'status' parameter name, not 'lifecycle_status'
        visibility=visibility,
        trust_level=trust_level,
        trace_id=trace_id,
        target_id=target_id,
        tag=tag,
    )
    return EnhancedMemoryRecordsPayload(
        layer=normalized if normalized in {"semantic", "procedural", "episodic"} else "all",
        limit=limit,
        items=[build_enhanced_memory_record_item(record) for record in records],
    )


def build_enhanced_memory_search_payload(
    service: _EnhancedMemoryServiceLike,
    *,
    query: str,
    limit: int,
    trace_id: str | None,
    target_id: str | None,
) -> EnhancedMemorySearchPayload:
    hits = service.recall(
        query=query,
        limit=limit,
        trace_id=trace_id,
        target_id=target_id,
    )
    return EnhancedMemorySearchPayload(
        query=query,
        limit=limit,
        trace_id=trace_id,
        target_id=target_id,
        items=[build_recall_hit_item(hit) for hit in hits],
    )


def build_enhanced_memory_audit_payload(
    service: _EnhancedMemoryServiceLike,
    *,
    memory_id: str,
    limit: int,
) -> EnhancedMemoryAuditPayload:
    return EnhancedMemoryAuditPayload(
        memory_id=memory_id,
        limit=limit,
        items=[
            build_memory_audit_event_item(event)
            for event in service.list_audit_events(memory_id=memory_id, limit=limit)
        ],
    )
