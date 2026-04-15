"""
Events Commons Module
Event stream session management and query layer
Extracted from events.py for Facade-First architecture
"""

from __future__ import annotations

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
        self.transcript_store = None
        self.session = None
        self._initialized = False
        
    async def initialize(self) -> bool:
        """Initialize event stream session dependencies"""
        try:
            self.runtime = getattr(self.app_state, "runtime", None)
            if self.runtime is None:
                logger.warning("BrainRuntime not attached to app state")
                return False
                
            self.transcript_store = getattr(self.app_state, "transcript_store", None)
            if self.transcript_store is None:
                logger.warning("TranscriptStore not attached to app state")
                return False
            
            self.session = getattr(self.app_state, "session", None)
            if self.session is not None and not hasattr(self.session, "advance_turn"):
                # Duck type check failed
                self.session = None
            
            self._initialized = True
            logger.info("EventStreamSession initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize EventStreamSession: {e}")
            return False


async def get_or_create_event_session(websocket: WebSocket) -> EventStreamSession:
    """Factory for creating and initializing WebSocket event sessions"""
    session = EventStreamSession(websocket)
    await session.initialize()
    return session


async def get_active_connections(request: Request) -> List[Dict[str, Any]]:
    """Query active WebSocket connections status"""
    try:
        app_state = request.app.state
        
        # Get connection manager or similar if available
        # For now return empty list as placeholder
        connections = []
        
        logger.info(f"Active connections count: {len(connections)}")
        return connections
        
    except Exception as e:
        logger.error(f"Failed to get active connections: {e}")
        return []


async def get_event_statistics(request: Request) -> Dict[str, Any]:
    """Query event stream statistics"""
    try:
        app_state = request.app.state
        transcript_store = getattr(app_state, "transcript_store", None)
        
        stats = {
            "active_connections": 0,
            "total_entries": 0,
            "current_revision": 0,
            "status": "healthy"
        }
        
        if transcript_store is not None:
            try:
                entries = transcript_store.get_entries_snapshot()
                stats["total_entries"] = len(entries)
                stats["current_revision"] = transcript_store.get_revision()
            except Exception as e:
                logger.warning(f"Failed to get transcript store stats: {e}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get event statistics: {e}")
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
        logger.debug(f"Error while waiting for disconnect: {e}")
        return


async def setup_transcript_stream(
    session: EventStreamSession,
    last_entry_id: Optional[str] = None
) -> tuple[int, int]:
    """Setup transcript stream with entry position tracking
    
    Returns:
        (last_sent_index, last_seen_revision) tuple
    """
    try:
        current_entries = session.transcript_store.get_entries_snapshot()
        
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
        
        last_seen_revision = session.transcript_store.get_revision()
        
        logger.info(f"Transcript stream setup: index={last_sent_index}, revision={last_seen_revision}")
        
        return last_sent_index, last_seen_revision
        
    except Exception as e:
        logger.error(f"Failed to setup transcript stream: {e}")
        return -1, -1
