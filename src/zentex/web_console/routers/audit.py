"""
Audit Router Module (v5)
Audit query endpoints
Facade-First route layer extracted from audit.py
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from typing_extensions import Annotated

from zentex.web_console.contracts.audit import AuditPagePayload, TurnAuditPagePayload
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.dependencies import get_kernel_service_facade
from .audit_commons import (
    query_model_provider_traces,
    query_turn_audit_milestones,
    query_audit_entries,
)

router = APIRouter()


@router.get("/audit/model-provider", response_model=List[ModelProviderTraceItem])
async def list_model_provider_audit_traces(
    facade: Annotated[object, Depends(get_kernel_service_facade)],
) -> List[ModelProviderTraceItem]:
    """
    Get audit traces for all model provider calls
    
    Returns:
        List of model provider trace items with timing and token information
    """
    return await query_model_provider_traces(facade)


@router.get("/audit/turns", response_model=TurnAuditPagePayload)
async def list_turn_audit_milestones(
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
    return await query_turn_audit_milestones(facade, page=page, page_size=page_size)


@router.get("/audits", response_model=AuditPagePayload)
async def list_audit_entries(
    facade: Annotated[object, Depends(get_kernel_service_facade)],
    page: int = 1,
    page_size: int = 40,
    request_id: Optional[str] = None,
    decision_id: Optional[str] = None,
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
        facade,
        page=page,
        page_size=page_size,
        request_id=request_id,
        decision_id=decision_id
    )
