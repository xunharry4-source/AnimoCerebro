from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from zentex.web_console.contracts.memory import (
    EnhancedMemoryAuditPayload,
    EnhancedMemoryOverviewPayload,
    EnhancedMemoryRecordsPayload,
    EnhancedMemorySearchPayload,
    EnhancedMemoryRecordItem,
    UpdateEnhancedMemoryRequest,
)
from zentex.web_console.dependencies import get_enhanced_memory_service
from zentex.web_console.services.memory import (
    build_enhanced_memory_audit_payload,
    build_enhanced_memory_overview,
    build_enhanced_memory_records_payload,
    build_enhanced_memory_record_item,
    build_enhanced_memory_search_payload,
)


router = APIRouter()


@router.get("/memory/enhanced/overview", response_model=EnhancedMemoryOverviewPayload)
def get_enhanced_memory_overview(
    service=Depends(get_enhanced_memory_service),
) -> EnhancedMemoryOverviewPayload:
    return build_enhanced_memory_overview(service)


@router.get("/memory/enhanced/records", response_model=EnhancedMemoryRecordsPayload)
def list_enhanced_memory_records(
    layer: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = None,
    visibility: str | None = None,
    trust_level: str | None = None,
    trace_id: str | None = None,
    target_id: str | None = None,
    tag: str | None = None,
    service=Depends(get_enhanced_memory_service),
) -> EnhancedMemoryRecordsPayload:
    return build_enhanced_memory_records_payload(
        service,
        layer=layer,
        limit=limit,
        status=status,
        visibility=visibility,
        trust_level=trust_level,
        trace_id=trace_id,
        target_id=target_id,
        tag=tag,
    )


@router.get("/memory/enhanced/search", response_model=EnhancedMemorySearchPayload)
def search_enhanced_memory(
    query: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    trace_id: str | None = None,
    target_id: str | None = None,
    service=Depends(get_enhanced_memory_service),
) -> EnhancedMemorySearchPayload:
    return build_enhanced_memory_search_payload(
        service,
        query=query,
        limit=limit,
        trace_id=trace_id,
        target_id=target_id,
    )


@router.get("/memory/enhanced/{memory_id}", response_model=EnhancedMemoryRecordItem)
def get_enhanced_memory_record(
    memory_id: str,
    service=Depends(get_enhanced_memory_service),
) -> EnhancedMemoryRecordItem:
    record = service.get_managed_record(memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory record not found.")
    return build_enhanced_memory_record_item(record)


@router.get("/memory/enhanced/{memory_id}/audit", response_model=EnhancedMemoryAuditPayload)
def get_enhanced_memory_audit(
    memory_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    service=Depends(get_enhanced_memory_service),
) -> EnhancedMemoryAuditPayload:
    record = service.get_managed_record(memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory record not found.")
    return build_enhanced_memory_audit_payload(service, memory_id=memory_id, limit=limit)


@router.post("/memory/enhanced/{memory_id}/management", response_model=EnhancedMemoryRecordItem)
def update_enhanced_memory_management(
    memory_id: str,
    request: UpdateEnhancedMemoryRequest,
    service=Depends(get_enhanced_memory_service),
) -> EnhancedMemoryRecordItem:
    try:
        record = service.update_management_state(
            memory_id,
            status=request.status,
            visibility=request.visibility,
            trust_level=request.trust_level,
            management_note=request.management_note,
            correction_note=request.correction_note,
            operator=request.operator,
            reason=request.reason,
            supersedes_memory_id=request.supersedes_memory_id,
            superseded_by_memory_id=request.superseded_by_memory_id,
            mark_verified=request.mark_verified,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory record not found.") from exc
    return build_enhanced_memory_record_item(record)
