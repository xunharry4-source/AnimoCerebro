from __future__ import annotations
"""Memory Routes v3 - Refactored with Facade-First Design

⚠️  MODULARIZATION CONSTRAINT - MAX 150 LINES
════════════════════════════════════════════════════════════════════
This module MUST NOT exceed 150 lines. All business logic extracted to:
  - memory_commons.py: Shared memory queries and sessions
  - memory_handlers.py: Memory-specific operations

This file contains ONLY route definitions that delegate to services.
════════════════════════════════════════════════════════════════════
"""


import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from zentex.web_console.contracts.memory import (
    EnhancedMemoryAuditPayload,
    EnhancedMemoryOverviewPayload,
    EnhancedMemoryRecordsPayload,
    EnhancedMemorySearchPayload,
    EnhancedMemoryRecordItem,
    UpdateEnhancedMemoryRequest,
)

# Import service layer
from .memory_commons import (
    get_memory_overview,
    list_memory_records,
    search_memory,
    get_memory_record_detail,
    get_memory_audit_log,
)
from .memory_handlers import (
    update_memory_record_management,
    trigger_consolidation_cycle,
    clear_memory_verification_flag,
)
from .cognition_handlers import handle_get_consolidation_cycles
from zentex.web_console.dependencies import get_consolidation_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/overview", response_model=EnhancedMemoryOverviewPayload)
async def get_overview(request: Request) -> EnhancedMemoryOverviewPayload:
    """Get memory statistics overview."""
    return await get_memory_overview(request)


@router.get("/records", response_model=EnhancedMemoryRecordsPayload)
async def list_records(
    request: Request,
    layer: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = None,
    visibility: Optional[str] = None,
    trust_level: Optional[str] = None,
    trace_id: Optional[str] = None,
    target_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> EnhancedMemoryRecordsPayload:
    """List memory records with filtering."""
    return await list_memory_records(
        request,
        layer=layer,
        limit=limit,
        lifecycle_status=status,
        visibility=visibility,
        trust_level=trust_level,
        trace_id=trace_id,
        target_id=target_id,
        tag=tag,
    )


@router.get("/search", response_model=EnhancedMemorySearchPayload)
async def search_records(
    request: Request,
    query: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    trace_id: Optional[str] = None,
    target_id: Optional[str] = None,
) -> EnhancedMemorySearchPayload:
    """Search memory records semantically."""
    return await search_memory(
        request,
        query=query,
        limit=limit,
        trace_id=trace_id,
        target_id=target_id,
    )


@router.get("/consolidation-cycles")
async def get_consolidation_cycle_history(
    consolidation_engine=Depends(get_consolidation_engine),
):
    """Compatibility alias for consolidation cycle history under the memory namespace."""
    return handle_get_consolidation_cycles(consolidation_engine)


@router.get("/{memory_id}", response_model=EnhancedMemoryRecordItem)
async def get_record_detail(
    request: Request,
    memory_id: str,
) -> EnhancedMemoryRecordItem:
    """Get memory record details."""
    return await get_memory_record_detail(request, memory_id)


@router.get(
    "/{memory_id}/audit",
    response_model=EnhancedMemoryAuditPayload,
)
async def get_record_audit(
    request: Request,
    memory_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> EnhancedMemoryAuditPayload:
    """Get audit trail for memory record."""
    return await get_memory_audit_log(request, memory_id, limit=limit)


@router.post(
    "/{memory_id}/management",
    response_model=EnhancedMemoryRecordItem,
)
async def update_record_management(
    request: Request,
    memory_id: str,
    update_request: UpdateEnhancedMemoryRequest,
) -> EnhancedMemoryRecordItem:
    """Update memory record management state."""
    return await update_memory_record_management(request, memory_id, update_request)


@router.post("/consolidation/trigger")
async def trigger_consolidation(
    request: Request,
    force_auto_organize: bool = Query(default=False),
) -> dict[str, object]:
    """Trigger manual memory consolidation cycle."""
    return await trigger_consolidation_cycle(request, force_auto_organize=force_auto_organize)
