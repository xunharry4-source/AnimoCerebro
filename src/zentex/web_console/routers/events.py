"""
Events Router Module (v4)
WebSocket event streaming endpoints
Facade-First route layer extracted from events.py
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Any

from fastapi import APIRouter, WebSocket, Query, Request, WebSocketDisconnect

from .events_commons import (
    get_or_create_event_session,
    get_active_connections,
    get_event_statistics,
    wait_for_disconnect,
    setup_transcript_stream,
)
from .events_handlers import (
    validate_event_stream_session,
    send_event_message,
    process_transcript_entries,
    wait_for_new_entries,
    build_overview_update,
    handle_stream_error,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@router.websocket("/events/stream")
async def stream_events(websocket: WebSocket, last_entry_id: Optional[str] = Query(None)):
    """
    WebSocket endpoint for real-time event streaming
    
    Streams transcript entries and overview updates as they become available.
    
    Query Parameters:
        last_entry_id: Optional entry ID to start streaming from (delta mode)
        
    WebSocket Message Format:
        {
            "event": {...transcript entry...},
            "overview": {...system overview...}
        }
    
    Usage:
        ws://localhost:8000/api/web/events/stream
        ws://localhost:8000/api/web/events/stream?last_entry_id=entry-123
    """
    await websocket.accept()
    
    # Initialize session
    session = await get_or_create_event_session(websocket)
    if not await validate_event_stream_session(session):
        await websocket.close(code=1011, reason="Session initialization failed")
        return
    
    # Setup transcript tracking
    last_sent_index, last_seen_revision = await setup_transcript_stream(session, last_entry_id)
    if last_sent_index < 0:
        await websocket.close(code=1011, reason="Failed to setup transcript stream")
        return
    
    # Create disconnect monitoring task
    disconnect_task = asyncio.create_task(wait_for_disconnect(websocket))
    
    try:
        while True:
            # Check if client disconnected
            if disconnect_task.done():
                logger.info("Client disconnected, closing stream")
                return
            
            # Get current state
            current_entries = session.transcript_store.get_entries_snapshot()
            newest_index = len(current_entries) - 1
            
            # Wait for new entries if none available
            if newest_index <= last_sent_index:
                updated = await wait_for_new_entries(
                    websocket,
                    session.transcript_store,
                    last_seen_revision,
                    timeout=3.0
                )
                
                if not updated:
                    # Timeout or disconnect
                    if disconnect_task.done():
                        return
                    continue
                
                last_seen_revision = session.transcript_store.get_revision()
                continue
            
            # Update session reference if changed
            if session.session is None and hasattr(websocket.app.state, "session"):
                new_session = getattr(websocket.app.state, "session", None)
                if new_session is not None and hasattr(new_session, "advance_turn"):
                    session.session = new_session
            
            # Build overview and send entries
            overview = await build_overview_update(session, websocket)
            if overview is None:
                logger.warning("Failed to build overview, skipping update")
                continue
            
            # Process new entries
            if newest_index > last_sent_index:
                from zentex.web_console.contracts.runtime import TranscriptStreamMessage
                from zentex.web_console.transcript_serialization import serialize_transcript_entry
                
                for entry in current_entries[last_sent_index + 1:]:
                    if disconnect_task.done():
                        return
                    
                    try:
                        message = TranscriptStreamMessage(
                            event=serialize_transcript_entry(entry),
                            overview=overview,
                        )
                        success = await send_event_message(websocket, message)
                        if not success:
                            logger.warning("Failed to send message, stopping stream")
                            return
                    except Exception as e:
                        logger.error(f"Error sending entry: {e}")
                        return
                
                last_sent_index = newest_index
                last_seen_revision = session.transcript_store.get_revision()
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        return
        
    except RuntimeError as e:
        logger.error(f"Runtime error in stream: {e}")
        return
        
    except Exception as e:
        handled = await handle_stream_error(websocket, e)
        if not handled:
            return
            
    finally:
        disconnect_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# REST Endpoints (Query)
# ============================================================================

@router.get("/events/status")
async def get_events_status(request: Request) -> dict:
    """Get current event stream status and statistics"""
    return await get_event_statistics(request)


@router.get("/events/connections")
async def list_active_connections(request: Request) -> dict:
    """List all active WebSocket connections"""
    connections = await get_active_connections(request)
    return {
        "connections": connections,
        "count": len(connections),
        "status": "ok"
    }


@router.get("/events/healthcheck")
async def events_healthcheck() -> dict:
    """Health check endpoint for event stream service"""
    return {
        "status": "healthy",
        "service": "events",
        "version": "4.0",
        "component": "transcript-stream"
    }
