from __future__ import annotations

"""Builders for enhanced memory management web-console payloads."""

from zentex.memory.enhanced import (
    EnhancedMemoryService,
    ManagedEnhancedMemoryRecord,
    MemoryAuditEvent,
    MemoryRecallHit,
)
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


def build_enhanced_memory_record_item(record: ManagedEnhancedMemoryRecord) -> EnhancedMemoryRecordItem:
    return EnhancedMemoryRecordItem.model_validate(record.model_dump())


def build_recall_hit_item(hit: MemoryRecallHit) -> EnhancedMemoryRecallHitItem:
    return EnhancedMemoryRecallHitItem.model_validate(hit.model_dump())


def build_memory_audit_event_item(event: MemoryAuditEvent) -> EnhancedMemoryAuditEventItem:
    return EnhancedMemoryAuditEventItem.model_validate(event.model_dump())


def build_enhanced_memory_overview(
    service: EnhancedMemoryService,
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
    service: EnhancedMemoryService,
    *,
    layer: str,
    limit: int,
    status: str | None,
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
        status=status,
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
    service: EnhancedMemoryService,
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
    service: EnhancedMemoryService,
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
