"""
Audit Commons Module
Audit query layer and session management
Extracted from audit.py for Facade-First architecture
"""

from typing import List, Optional
import logging

from zentex.web_console.contracts.audit import AuditPagePayload, TurnAuditPagePayload
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.services.audit import (
    build_audit_page,
    build_model_provider_traces,
    build_turn_audit_page
)

logger = logging.getLogger(__name__)


class AuditSession:
    """Request-scoped audit query session"""
    
    def __init__(self, facade: object):
        self.facade = facade
        self.transcript_store = None
        self._initialized = False
        
    async def initialize(self) -> bool:
        """Initialize audit session with dependencies"""
        try:
            self.transcript_store = self.facade.get_transcript_store()
            self._initialized = True
            logger.info("AuditSession initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AuditSession: {e}")
            return False


async def get_or_create_audit_session(facade: object) -> AuditSession:
    """Factory for creating audit sessions"""
    session = AuditSession(facade)
    await session.initialize()
    return session


async def query_model_provider_traces(facade: object) -> List[ModelProviderTraceItem]:
    """Query audit traces for model provider calls"""
    try:
        traces = build_model_provider_traces(facade)
        logger.info(f"Retrieved {len(traces)} model provider traces")
        return traces
    except Exception as e:
        logger.error(f"Failed to query model provider traces: {e}")
        return []


async def query_turn_audit_milestones(
    facade: object,
    page: int = 1,
    page_size: int = 40
) -> TurnAuditPagePayload:
    """Query turn-level audit milestones with pagination"""
    try:
        entries = facade.get_transcript_store().get_entries_snapshot()
        payload = build_turn_audit_page(entries, page=page, page_size=page_size)
        logger.info(f"Retrieved turn audit page {page} (size={page_size})")
        return payload
    except Exception as e:
        logger.error(f"Failed to query turn audit milestones: {e}")
        return TurnAuditPagePayload(items=[], total=0, page=page, page_size=page_size)


async def query_audit_entries(
    facade: object,
    page: int = 1,
    page_size: int = 40,
    request_id: Optional[str] = None,
    decision_id: Optional[str] = None
) -> AuditPagePayload:
    """Query audit entries with optional filtering and pagination"""
    try:
        entries = facade.get_transcript_store().get_entries_snapshot()
        payload = build_audit_page(
            entries,
            page=page,
            page_size=page_size,
            request_id=request_id,
            decision_id=decision_id
        )
        logger.info(f"Retrieved audit entries page {page} (size={page_size}, filters={bool(request_id or decision_id)})")
        return payload
    except Exception as e:
        logger.error(f"Failed to query audit entries: {e}")
        return AuditPagePayload(items=[], total=0, page=page, page_size=page_size)
