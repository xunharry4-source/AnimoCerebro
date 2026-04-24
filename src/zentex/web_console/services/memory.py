from __future__ import annotations
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


from typing import Any, Protocol

from zentex.web_console.contracts.memory import (
    EnhancedMemoryAuditEventItem,
    EnhancedMemoryAuditPayload,
    EnhancedMemoryOverviewPayload,
    MemoryRecordDiagnosticsPayload,
    MemoryRecordManifestItem,
    MemoryRepairAllPayload,
    MemoryRepairSchedulerStatusPayload,
    MemoryRepairTicketItem,
    EnhancedMemoryRecordItem,
    EnhancedMemoryRecallHitItem,
    EnhancedMemoryRecordsPayload,
    EnhancedMemorySearchPayload,
    MemoryBackendStatusItem,
)


class _ModelDumpLike(Protocol):
    def model_dump(self) -> dict[str, Any]: ...


class _EnhancedMemoryServiceLike(Protocol):
    def query_managed_records(self, *args: Any, **kwargs: Any) -> list[Any]: ...

    def list_managed_records(self, *args: Any, **kwargs: Any) -> list[Any]: ...

    def list_semantic_records(self) -> list[Any]: ...

    def list_procedural_records(self) -> list[Any]: ...

    def list_episodic_records(self) -> list[Any]: ...

    def list_projection_failures(self) -> list[Any]: ...

    def list_initialization_failures(self) -> list[Any]: ...

    def list_governance_failures(self) -> list[Any]: ...

    def get_health_snapshot(self) -> dict[str, Any]: ...

    def get_backend_status(self) -> list[Any]: ...

    def recall(self, *args: Any, **kwargs: Any) -> list[Any]: ...

    def list_audit_events(self, *args: Any, **kwargs: Any) -> list[Any]: ...

    def get_record_header(self, memory_id: str) -> Any: ...

    def get_record_manifest(self, memory_id: str) -> Any: ...

    def verify_record(self, memory_id: str) -> Any: ...

    def repair_record(self, memory_id: str) -> Any: ...

    def repair_all(self) -> list[Any]: ...


def build_enhanced_memory_record_item(record: _ModelDumpLike) -> EnhancedMemoryRecordItem:
    raw = record.model_dump()
    allowed = {
        key: raw[key]
        for key in EnhancedMemoryRecordItem.model_fields
        if key in raw
    }
    return EnhancedMemoryRecordItem.model_validate(allowed)


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
    health_snapshot = service.get_health_snapshot()
    return EnhancedMemoryOverviewPayload(
        semantic_count=len(service.list_semantic_records()),
        procedural_count=len(service.list_procedural_records()),
        episodic_count=len(service.list_episodic_records()),
        active_count=sum(1 for item in managed if item.status == "active"),
        deprecated_count=sum(1 for item in managed if item.status == "deprecated"),
        archived_count=sum(1 for item in managed if item.status == "archived"),
        suspect_count=sum(1 for item in managed if item.trust_level == "suspect"),
        health_status=str(health_snapshot.get("health_status", "unknown")),
        projection_failures=service.list_projection_failures(),
        initialization_failures=service.list_initialization_failures(),
        governance_failures=service.list_governance_failures(),
        package_imports=int(health_snapshot.get("package_imports", 0)),
        contamination_events=int(health_snapshot.get("contamination_events", 0)),
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
    lifecycle_status: Optional[str],
    visibility: Optional[str],
    trust_level: Optional[str],
    trace_id: Optional[str],
    target_id: Optional[str],
    tag: Optional[str],
) -> EnhancedMemoryRecordsPayload:
    normalized = layer.lower()
    query_fn = getattr(service, "query_managed_records", None) or service.list_managed_records
    records = query_fn(
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
    trace_id: Optional[str],
    target_id: Optional[str],
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


def build_memory_repair_ticket_item(ticket: _ModelDumpLike) -> MemoryRepairTicketItem:
    return MemoryRepairTicketItem.model_validate(ticket.model_dump())


def build_memory_record_diagnostics_payload(
    service: _EnhancedMemoryServiceLike,
    *,
    memory_id: str,
) -> MemoryRecordDiagnosticsPayload:
    header = service.get_record_header(memory_id)
    if header is None:
        raise KeyError(memory_id)
    manifest = service.get_record_manifest(memory_id)
    verification = service.verify_record(memory_id)
    return MemoryRecordDiagnosticsPayload(
        memory_id=memory_id,
        storage_schema_version=int(getattr(header, "storage_schema_version", 1)),
        record_health_status=str(getattr(header, "record_health_status", "unknown")),
        repair_status=str(getattr(header, "repair_status", "unknown")),
        header=header.model_dump(mode="json"),
        manifest=MemoryRecordManifestItem.model_validate(manifest.model_dump()) if manifest is not None else None,
        verification=build_memory_repair_ticket_item(verification) if verification is not None else None,
    )


def build_memory_repair_all_payload(
    *,
    items: list[_ModelDumpLike],
    scheduler_status: dict[str, Any],
    triggered_by: str = "web_console",
) -> MemoryRepairAllPayload:
    return MemoryRepairAllPayload(
        triggered_by=triggered_by,
        scheduler=MemoryRepairSchedulerStatusPayload.model_validate(scheduler_status),
        items=[build_memory_repair_ticket_item(item) for item in items],
    )
