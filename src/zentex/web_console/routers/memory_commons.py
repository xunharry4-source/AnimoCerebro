"""Memory Query Commons - Shared Memory Access Layer

⚠️  SERVICE LAYER - QUERIES & SESSIONS
════════════════════════════════════════════════════════════════════
This module centralizes all memory read operations and session management.
All write operations and route definitions are in separate modules to maintain
clear separation of concerns.
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional
from fastapi import Request, HTTPException

from zentex.web_console.contracts.memory import (
    EnhancedMemoryAuditPayload,
    EnhancedMemoryOverviewPayload,
    EnhancedMemoryRecordsPayload,
    EnhancedMemorySearchPayload,
    EnhancedMemoryRecordItem,
)
from zentex.web_console.dependencies import (
    get_enhanced_memory_service,
    get_consolidation_engine,
)
from zentex.web_console.services.memory import (
    build_enhanced_memory_audit_payload,
    build_enhanced_memory_overview,
    build_enhanced_memory_records_payload,
    build_enhanced_memory_record_item,
    build_enhanced_memory_search_payload,
)

logger = logging.getLogger(__name__)


class MemorySession:
    """Request-scoped memory session management.
    
    Encapsulates:
      - enhanced_memory_service: Main memory service
      - consolidation_engine: Memory consolidation
      - Request context
    """

    def __init__(self, request: Request):
        """Initialize memory session from request dependencies."""
        try:
            self.service = get_enhanced_memory_service(request)
            self.consolidation_engine = get_consolidation_engine(request)
        except (AttributeError, TypeError) as e:
            logger.error(f"Failed to initialize MemorySession: {e}")
            raise HTTPException(status_code=503, detail="Memory service unavailable") from e

    def is_available(self) -> bool:
        """Check if memory service is available."""
        return self.service is not None


async def get_or_create_memory_session(request: Request) -> MemorySession:
    """Get or create a memory session for the request.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        MemorySession instance
        
    Raises:
        HTTPException (503): If memory service is unavailable
    """
    session = MemorySession(request)
    if not session.is_available():
        raise HTTPException(status_code=503, detail="Memory service not initialized")
    return session


# Query Builders - Read-Only Operations


async def get_memory_overview(request: Request) -> EnhancedMemoryOverviewPayload:
    """Build memory statistics overview.
    
    Returns aggregated statistics across all memory layers:
    - Semantic, Procedural, Episodic counts
    - Status distribution (active, deprecated, archived)
    - Backend information
    
    Args:
        request: FastAPI Request
        
    Returns:
        EnhancedMemoryOverviewPayload with statistics
    """
    session = await get_or_create_memory_session(request)
    try:
        return build_enhanced_memory_overview(session.service)
    except TimeoutError:
        logger.warning("Memory overview query timed out; returning zeros")
        return EnhancedMemoryOverviewPayload(
            semantic_count=0,
            procedural_count=0,
            episodic_count=0,
            active_count=0,
            deprecated_count=0,
            archived_count=0,
            suspect_count=0,
            projection_failures=[],
            backends=[],
        )
    except Exception as exc:
        logger.error(f"Error fetching memory overview: {exc}")
        return EnhancedMemoryOverviewPayload(
            semantic_count=0,
            procedural_count=0,
            episodic_count=0,
            active_count=0,
            deprecated_count=0,
            archived_count=0,
            suspect_count=0,
            projection_failures=[],
            backends=[],
        )


async def list_memory_records(
    request: Request,
    layer: str = "all",
    limit: int = 50,
    lifecycle_status: Optional[str] = None,
    visibility: Optional[str] = None,
    trust_level: Optional[str] = None,
    trace_id: Optional[str] = None,
    target_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> EnhancedMemoryRecordsPayload:
    """List memory records with filtering and pagination.
    
    Args:
        request: FastAPI Request
        layer: Memory layer ("all", "semantic", "procedural", "episodic")
        limit: Maximum records to return (1-200)
        lifecycle_status: Filter by status
        visibility: Filter by visibility
        trust_level: Filter by trust level
        trace_id: Filter by trace ID
        target_id: Filter by target ID
        tag: Filter by tag
        
    Returns:
        EnhancedMemoryRecordsPayload with filtered records
    """
    session = await get_or_create_memory_session(request)
    try:
        return build_enhanced_memory_records_payload(
            session.service,
            layer=layer,
            limit=limit,
            lifecycle_status=lifecycle_status,
            visibility=visibility,
            trust_level=trust_level,
            trace_id=trace_id,
            target_id=target_id,
            tag=tag,
        )
    except TimeoutError:
        logger.warning("Memory records query timed out; returning empty results")
        return EnhancedMemoryRecordsPayload(layer=layer, limit=limit, items=[])
    except Exception as exc:
        logger.error(f"Error fetching memory records: {exc}")
        return EnhancedMemoryRecordsPayload(layer=layer, limit=limit, items=[])


async def search_memory(
    request: Request,
    query: str,
    limit: int = 10,
    trace_id: Optional[str] = None,
    target_id: Optional[str] = None,
) -> EnhancedMemorySearchPayload:
    """Semantic search across memory records.
    
    Args:
        request: FastAPI Request
        query: Search query (min 1 character)
        limit: Maximum results (1-50)
        trace_id: Optional trace filter
        target_id: Optional target filter
        
    Returns:
        EnhancedMemorySearchPayload with search results
    """
    session = await get_or_create_memory_session(request)
    try:
        return build_enhanced_memory_search_payload(
            session.service,
            query=query,
            limit=limit,
            trace_id=trace_id,
            target_id=target_id,
        )
    except TimeoutError:
        logger.warning(f"Memory search for query '{query}' timed out")
        return EnhancedMemorySearchPayload(query=query, limit=limit, items=[])
    except Exception as exc:
        logger.error(f"Error searching memory: {exc}")
        return EnhancedMemorySearchPayload(query=query, limit=limit, items=[])


async def get_memory_record_detail(
    request: Request,
    memory_id: str,
) -> EnhancedMemoryRecordItem:
    """Get detailed information about a memory record.
    
    Args:
        request: FastAPI Request
        memory_id: Memory record ID
        
    Returns:
        EnhancedMemoryRecordItem with full record details
        
    Raises:
        HTTPException (404): If record not found
    """
    session = await get_or_create_memory_session(request)
    record = session.service.get_managed_record(memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory record not found.")
    return build_enhanced_memory_record_item(record)


async def get_memory_audit_log(
    request: Request,
    memory_id: str,
    limit: int = 50,
) -> EnhancedMemoryAuditPayload:
    """Get audit trail for a memory record.
    
    Includes:
    - Modification history
    - Status changes
    - Operator actions
    - Timestamps
    
    Args:
        request: FastAPI Request
        memory_id: Memory record ID
        limit: Maximum audit entries (1-200)
        
    Returns:
        EnhancedMemoryAuditPayload with audit history
        
    Raises:
        HTTPException (404): If record not found
    """
    session = await get_or_create_memory_session(request)
    record = session.service.get_managed_record(memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory record not found.")
    return build_enhanced_memory_audit_payload(
        session.service,
        memory_id=memory_id,
        limit=limit,
    )
