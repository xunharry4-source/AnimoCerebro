"""
Audit Router Module (v5)
Audit query endpoints
Facade-First route layer extracted from audit.py
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from typing_extensions import Annotated

from zentex.web_console.contracts.audit import AuditGraphPayload, AuditPagePayload, AuditTraceStartsPagePayload, TurnAuditPagePayload
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.dependencies import get_kernel_service_facade
from .audit_commons import (
    query_audit_graph,
    query_flow_health,
    query_model_provider_traces,
    query_turn_audit_milestones,
    query_audit_entries,
    query_trace_starts,
)

router = APIRouter()


@router.get("/audit/flow-health")
async def list_audit_flow_health(
    request: Request,
    limit: int = 100,
    flow_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[dict]:
    return await query_flow_health(
        request,
        limit=limit,
        flow_type=flow_type,
        status=status,
    )


@router.get("/audit/trace-starts", response_model=AuditTraceStartsPagePayload)
async def list_audit_trace_starts(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=40, ge=1, le=500),
) -> AuditTraceStartsPagePayload:
    return await query_trace_starts(request, page=page, page_size=page_size)


@router.get("/audit/trace-center/{mode}", response_model=AuditGraphPayload)
async def get_audit_trace_graph(
    mode: str,
    request: Request,
    facade: Annotated[object, Depends(get_kernel_service_facade)],
) -> AuditGraphPayload:
    return await query_audit_graph(request, facade, mode=mode)


@router.get("/audit/model-provider", response_model=List[ModelProviderTraceItem])
async def list_model_provider_audit_traces(
    request: Request,
    facade: Annotated[object, Depends(get_kernel_service_facade)],
) -> List[ModelProviderTraceItem]:
    """
    Get audit traces for all model provider calls
    
    Returns:
        List of model provider trace items with timing and token information
    """
    return await query_model_provider_traces(request, facade)


@router.get("/audit/turns", response_model=TurnAuditPagePayload)
async def list_turn_audit_milestones(
    request: Request,
    facade: Annotated[object, Depends(get_kernel_service_facade)],
    page: int = 1,
    page_size: int = 40,
) -> TurnAuditPagePayload:
    """
    Get turn-level audit milestones with pagination
    
    Args:
        page: Page number (1-indexed)
        page_size: Entries per page (default 40)
        
    Returns:
        Paginated turn audit milestones
    """
    return await query_turn_audit_milestones(request, facade, page=page, page_size=page_size)


@router.get("/audits", response_model=AuditPagePayload)
async def list_audit_entries(
    request: Request,
    facade: Annotated[object, Depends(get_kernel_service_facade)],
    page: int = 1,
    page_size: int = 40,
    request_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    source_module: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> AuditPagePayload:
    """
    Get audit entries with optional filtering and pagination
    
    Args:
        page: Page number (1-indexed)
        page_size: Entries per page (default 40)
        request_id: Filter by specific request ID
        decision_id: Filter by specific decision ID
        
    Returns:
        Paginated audit entries matching filters
    """
    return await query_audit_entries(
        request,
        facade,
        page=page,
        page_size=page_size,
        request_id=request_id,
        decision_id=decision_id,
        source_module=source_module,
        status=status,
        search=search,
    )
