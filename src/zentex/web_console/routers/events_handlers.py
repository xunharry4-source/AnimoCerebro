"""
Events Handlers Module
Event operations and message handling for WebSocket streams
Extracted from events.py for Facade-First architecture
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Any

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.exceptions import WebSocketException

from zentex.web_console.contracts.runtime import TranscriptStreamMessage
from zentex.web_console.dependencies import get_weight_assembler
from zentex.web_console.services.overview import build_overview_payload
from zentex.web_console.transcript_serialization import serialize_transcript_entry
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
            
        if session.transcript_store is None:
            logger.error("TranscriptStore not available in session")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Session validation failed: {e}")
        return False


async def send_event_message(
    websocket: WebSocket,
    message: TranscriptStreamMessage
) -> bool:
    """Send event message through WebSocket"""
    try:
        await websocket.send_json(message.model_dump(mode="json"))
        return True
        
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during send")
        return False
        
    except Exception as e:
        logger.error(f"Failed to send event message: {e}")
        raise WebSocketException(code=1011, reason=str(e))


async def process_transcript_entries(
    websocket: WebSocket,
    session: EventStreamSession,
    start_index: int,
    end_index: int,
    overview: Any
) -> int:
    """Process and send multiple transcript entries
    
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
        current_entries = session.transcript_store.get_entries_snapshot()
        entries_sent = 0
        
        for entry in current_entries[start_index + 1 : end_index + 1]:
            try:
                message = TranscriptStreamMessage(
                    event=serialize_transcript_entry(entry),
                    overview=overview,
                )
                success = await send_event_message(websocket, message)
                if not success:
                    logger.warning(f"Failed to send entry {entry.entry_id}")
                    break
                entries_sent += 1
                
            except Exception as e:
                logger.error(f"Error processing entry: {e}")
                break
        
        logger.info(f"Processed {entries_sent} transcript entries")
        return entries_sent
        
    except Exception as e:
        logger.error(f"Failed to process transcript entries: {e}")
        return 0


async def wait_for_new_entries(
    websocket: WebSocket,
    transcript_store: Any,
    current_revision: int,
    timeout: float = 3.0
) -> bool:
    """Wait for new entries in transcript store
    
    Args:
        websocket: WebSocket connection
        transcript_store: Transcript store to monitor
        current_revision: Current revision to check against
        timeout: Timeout in seconds
        
    Returns:
        True if new entries available, False on timeout or disconnect
    """
    try:
        disconnect_task = asyncio.create_task(_receive_disconnect_signal(websocket))
        revision_wait_task = asyncio.create_task(
            asyncio.to_thread(
                transcript_store.wait_for_revision_after,
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
            logger.warning(f"Wait for revision failed: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to wait for new entries: {e}")
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
            session.transcript_store,
            get_weight_assembler(websocket.app),
        )
        return overview
        
    except Exception as e:
        logger.error(f"Failed to build overview update: {e}")
        return None


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
        logger.error(f"Error handler failed: {e}")
        return False
