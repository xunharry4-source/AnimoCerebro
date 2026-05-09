from __future__ import annotations
"""
Events Commons Module
Event stream session management and query layer
Extracted from events.py for Facade-First architecture
"""


import asyncio
import logging
from typing import Optional, List, Any, Dict

from fastapi import Request, WebSocket

logger = logging.getLogger(__name__)


class EventStreamSession:
    """Request-scoped event stream session for WebSocket management"""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.app_state = websocket.app.state
        self.runtime = None
        self.audit_service = None
        self.session = None
        self._initialized = False
        
    async def initialize(self) -> bool:
        """Initialize event stream session dependencies"""
        try:
            self.runtime = getattr(self.app_state, "runtime", None)
            if self.runtime is None:
                # Soft failure: log but continue as BrainRuntime is deprecated
                logger.info("BrainRuntime not available (legacy mode disabled)")
                
            self.audit_service = getattr(self.app_state, "audit_service", None)
            if self.audit_service is None:
                logger.warning("AuditService not attached to app state")
                return False
            
            self.session = getattr(self.app_state, "session", None)
            if self.session is not None and not hasattr(self.session, "advance_turn"):
                # Duck type check failed
                self.session = None
            
            self._initialized = True
            logger.info("EventStreamSession initialized successfully")
            return True
            
        except Exception as e:
            logger.exception("Failed to initialize EventStreamSession")
            return False


async def get_or_create_event_session(websocket: WebSocket) -> EventStreamSession:
    """Factory for creating and initializing WebSocket event sessions"""
    session = EventStreamSession(websocket)
    await session.initialize()
    return session


async def get_active_connections(request: Request) -> List[Dict[str, Any]]:
    """Query active WebSocket connections status"""
    try:
        # Do not keep a placeholder implementation here. Returning an empty list as
        # if it were real runtime data would fake a healthy event-plane state and
        # destroy observability when connection tracking is actually unavailable.
        raise RuntimeError(
            "Active connections inspection is not implemented; refusing placeholder results."
        )
    except Exception as e:
        logger.exception("Failed to get active connections")
        return []


async def get_event_statistics(request: Request) -> Dict[str, Any]:
    """Query event stream statistics"""
    try:
        app_state = request.app.state
        audit_service = getattr(app_state, "audit_service", None)
        
        stats = {
            "active_connections": 0,
            "total_entries": 0,
            "current_revision": 0,
            "status": "healthy"
        }
        
        if audit_service is not None:
            try:
                entries = audit_service.list_recent_events()
                stats["total_entries"] = len(entries)
                stats["current_revision"] = audit_service.get_event_stream_revision()
            except Exception as e:
                logger.exception("Failed to get audit service stats")
        
        return stats
        
    except Exception as e:
        logger.exception("Failed to get event statistics")
        return {"status": "error", "error": str(e)}


async def wait_for_disconnect(websocket: WebSocket) -> None:
    """Wait for WebSocket disconnect message"""
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                logger.info("WebSocket disconnect received")
                return
    except Exception as e:
        logger.exception("Error while waiting for disconnect")
        return


async def setup_audit_event_stream(
    session: EventStreamSession,
    last_entry_id: Optional[str] = None
) -> tuple[int, int]:
    """Setup audit event stream with entry position tracking.
    
    Returns:
        (last_sent_index, last_seen_revision) tuple
    """
    try:
        current_entries = session.audit_service.list_recent_events()
        
        if last_entry_id:
            last_sent_index = next(
                (index for index, entry in enumerate(current_entries) 
                 if entry.entry_id == last_entry_id),
                len(current_entries) - 1,
            )
        else:
            # Real-time stream is delta-only by default
            # Historical events available via other endpoints
            last_sent_index = len(current_entries) - 1
        
        last_seen_revision = session.audit_service.get_event_stream_revision()
        
        logger.info(f"Audit event stream setup: index={last_sent_index}, revision={last_seen_revision}")
        
        return last_sent_index, last_seen_revision
        
    except Exception as e:
        # Do not smuggle a failed stream setup downstream as (-1, -1). That fakes a
        # valid stream cursor and makes later runtime faults look like "no events".
        logger.exception("Failed to setup audit event stream")
        raise
