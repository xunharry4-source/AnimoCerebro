from __future__ import annotations
"""
Events Router Module (v4)
WebSocket event streaming endpoints
Facade-First route layer extracted from events.py
"""


import asyncio
import logging
from typing import Optional, Any

from fastapi import APIRouter, WebSocket, Query, Request, WebSocketDisconnect

from .events_commons import (
    get_or_create_event_session,
    get_active_connections,
    get_event_statistics,
    wait_for_disconnect,
    setup_audit_event_stream,
)
from .events_handlers import (
    validate_event_stream_session,
    send_event_message,
    process_audit_events,
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
    
    Streams audit events and overview updates as they become available.
    
    Query Parameters:
        last_entry_id: Optional entry ID to start streaming from (delta mode)
        
    WebSocket Message Format:
        {
            "event": {...audit event...},
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
    
    # Setup audit event tracking
    try:
        last_sent_index, last_seen_revision = await setup_audit_event_stream(session, last_entry_id)
    except Exception as exc:
        logger.exception("Failed to initialize audit event stream in route layer")
        await websocket.close(code=1011, reason="Failed to setup audit event stream")
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
            current_entries = session.audit_service.list_recent_events()
            newest_index = len(current_entries) - 1
            
            # Wait for new entries if none available
            if newest_index <= last_sent_index:
                updated = await wait_for_new_entries(
                    websocket,
                    session.audit_service,
                    last_seen_revision,
                    timeout=3.0
                )
                
                if not updated:
                    # Timeout or disconnect
                    if disconnect_task.done():
                        return
                    continue
                
                last_seen_revision = session.audit_service.get_event_stream_revision()
                continue
            
            # Update session reference if changed
            if session.session is None and hasattr(websocket.app.state, "session"):
                new_session = getattr(websocket.app.state, "session", None)
                if new_session is not None and hasattr(new_session, "advance_turn"):
                    session.session = new_session
            
            # Build overview and send entries
            overview = await build_overview_update(session, websocket)
            
            # Process new entries
            if newest_index > last_sent_index:
                if disconnect_task.done():
                    return

                entries_sent = await process_audit_events(
                    websocket,
                    session,
                    last_sent_index,
                    newest_index,
                    overview,
                )
                if entries_sent != newest_index - last_sent_index:
                    logger.warning(
                        "Event stream terminated before all entries were sent; expected=%s sent=%s",
                        newest_index - last_sent_index,
                        entries_sent,
                    )
                    return

                last_sent_index = newest_index
                last_seen_revision = session.audit_service.get_event_stream_revision()
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        return
        
    except RuntimeError:
        logger.exception("Runtime error in stream")
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
            logger.exception("Failed to close websocket cleanly")


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
    has_connection_manager = hasattr(request.app.state, "connection_manager")
    return {
        "connections": connections,
        "count": len(connections),
        "status": "healthy" if has_connection_manager else "degraded",
        "degradation_reason": None if has_connection_manager else "connection_tracking_unavailable",
    }


@router.get("/events/healthcheck")
async def events_healthcheck(request: Request) -> dict:
    """Health check endpoint for event stream service"""
    runtime = getattr(request.app.state, "runtime", None)
    audit_service = getattr(request.app.state, "audit_service", None)
    healthy = runtime is not None and audit_service is not None
    return {
        # Do not hard-code healthy here. That would be a fake implementation when
        # the runtime or audit service is not even attached.
        "status": "healthy" if healthy else "degraded",
        "service": "events",
        "version": "4.0",
        "component": "audit-event-stream",
        "degradation_reason": None if healthy else "runtime_or_audit_service_unavailable",
    }
