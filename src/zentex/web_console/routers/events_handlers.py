from __future__ import annotations
"""
Events Handlers Module
Event operations and message handling for WebSocket streams
Extracted from events.py for Facade-First architecture
"""


import asyncio
import logging
from typing import Optional, Any

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.exceptions import WebSocketException

from zentex.web_console.contracts.runtime import AuditEventStreamMessage
from zentex.web_console.dependencies import get_weight_assembler
from zentex.web_console.services.overview import build_overview_payload
from zentex.web_console.audit_event_serialization import serialize_audit_event
from .events_commons import EventStreamSession

logger = logging.getLogger(__name__)


async def validate_event_stream_session(session: EventStreamSession) -> bool:
    """Validate event stream session is properly initialized"""
    try:
        if not session._initialized:
            logger.error("Event stream session not initialized")
            return False
        
        if session.runtime is None:
            logger.error("Runtime not available in session")
            return False
            
        if session.audit_service is None:
            logger.error("AuditService not available in session")
            return False
        
        return True
        
    except Exception as e:
        logger.exception("Session validation failed")
        return False


async def send_event_message(
    websocket: WebSocket,
    message: AuditEventStreamMessage
) -> bool:
    """Send event message through WebSocket"""
    try:
        await websocket.send_json(message.model_dump(mode="json"))
        return True
        
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during send")
        return False
        
    except Exception as e:
        logger.exception("Failed to send event message")
        raise WebSocketException(code=1011, reason=str(e))


async def process_audit_events(
    websocket: WebSocket,
    session: EventStreamSession,
    start_index: int,
    end_index: int,
    overview: Any
) -> int:
    """Process and send multiple audit events
    
    Args:
        websocket: WebSocket connection
        session: Event stream session
        start_index: Starting entry index (inclusive)
        end_index: Ending entry index (inclusive)
        overview: Overview payload to include with each message
        
    Returns:
        Number of entries sent successfully
    """
    try:
        current_entries = session.audit_service.list_recent_events()
        entries_sent = 0
        
        for entry in current_entries[start_index + 1 : end_index + 1]:
            try:
                message = AuditEventStreamMessage(
                    event=serialize_audit_event(entry),
                    overview=overview,
                )
                success = await send_event_message(websocket, message)
                if not success:
                    logger.warning(f"Failed to send entry {entry.entry_id}")
                    break
                entries_sent += 1
                
            except Exception as e:
                logger.exception("Error processing audit event")
                break
        
        logger.info(f"Processed {entries_sent} audit events")
        return entries_sent
        
    except Exception as e:
        logger.exception("Failed to process audit events")
        return 0


async def wait_for_new_entries(
    websocket: WebSocket,
    audit_service: Any,
    current_revision: int,
    timeout: float = 3.0
) -> bool:
    """Wait for new audit events.
    
    Args:
        websocket: WebSocket connection
        audit_service: Audit service to monitor
        current_revision: Current revision to check against
        timeout: Timeout in seconds
        
    Returns:
        True if new entries available, False on timeout or disconnect
    """
    try:
        disconnect_task = asyncio.create_task(_receive_disconnect_signal(websocket))
        revision_wait_task = asyncio.create_task(
            asyncio.to_thread(
                audit_service.wait_for_new_events,
                current_revision,
                timeout,
            )
        )
        
        done, pending = await asyncio.wait(
            {revision_wait_task, disconnect_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        # Clean up pending tasks
        for task in pending:
            task.cancel()
        
        if disconnect_task in done:
            logger.info("Disconnect signal received while waiting for entries")
            return False
        
        try:
            result = revision_wait_task.result()
            return result
        except Exception as e:
            logger.exception("Wait for revision failed")
            return False
            
    except Exception as e:
        logger.exception("Failed to wait for new entries")
        return False


async def _receive_disconnect_signal(websocket: WebSocket) -> None:
    """Helper to detect WebSocket disconnect"""
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
    except Exception:
        return


async def build_overview_update(
    session: EventStreamSession,
    websocket: WebSocket
) -> Any:
    """Build fresh overview payload for event streaming"""
    try:
        overview = build_overview_payload(
            session.runtime,
            session.session,
            session.audit_service,
            get_weight_assembler(websocket.app),
        )
        return overview
        
    except Exception as e:
        # Do not hide overview assembly failures behind a None sentinel. That makes
        # the stream look like it merely skipped one refresh while the runtime
        # overview is actually broken.
        logger.exception("Failed to build overview update")
        raise


async def handle_stream_error(
    websocket: WebSocket,
    error: Exception
) -> bool:
    """Handle stream errors gracefully
    
    Returns:
        True if connection should be kept, False if should close
    """
    try:
        if isinstance(error, WebSocketDisconnect):
            logger.info("Stream ended: client disconnected")
            return False
            
        if isinstance(error, RuntimeError):
            logger.warning(f"Runtime error in stream: {error}")
            return False
        
        logger.exception(f"Unexpected error in event stream: {error}")
        return False
        
    except Exception as e:
        logger.exception("Error handler failed")
        return False
