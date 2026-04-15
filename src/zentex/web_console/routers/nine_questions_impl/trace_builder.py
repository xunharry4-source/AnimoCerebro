"""Trace Detail Builder

Constructs detailed trace information for nine-question execution traces.
Handles transcript query, event extraction, and formatting.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from datetime import datetime

from fastapi import HTTPException, Request

from zentex.web_console.dependencies import get_kernel_service_facade

logger = logging.getLogger(__name__)


async def build_trace_detail(
    request: Request,
    trace_id: str,
    session_id: str,
) -> Optional[dict[str, Any]]:
    """
    Build detailed trace information
    
    Reconstructs execution trace from:
    1. Event Bus events
    2. Transcript store entries (if available)
    3. State snapshots
    
    Args:
        request: FastAPI request
        trace_id: ID of the trace to fetch
        session_id: Session ID context
    
    Returns:
        Dictionary with trace details, or None if not found
    """
    facade = get_kernel_service_facade(request)
    
    try:
        # Try to get trace from event bus first
        event_bus = facade.get_event_bus()
        
        # Build basic trace structure
        trace_detail = {
            "trace_id": trace_id,
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "events": [],
            "snapshots": [],
            "status": "completed",
        }
        
        # Try to query transcript store if available
        try:
            # Try to access transcript store through facade
            if hasattr(facade, "get_transcript_store"):
                transcript_store = facade.get_transcript_store()
                
                if transcript_store and hasattr(transcript_store, "query"):
                    # Query entries for this trace
                    entries = await transcript_store.query(
                        filters={"trace_id": trace_id},
                        limit=100,
                    )
                    
                    # Process entries into events
                    for entry in entries:
                        event = {
                            "type": getattr(entry, "event_type", "unknown"),
                            "timestamp": str(getattr(entry, "timestamp", "")),
                            "data": getattr(entry, "data", {}),
                        }
                        trace_detail["events"].append(event)

        except Exception as e:
            logger.debug(f"Could not query transcript store: {e}")
        
        # If no events found, this trace effectively doesn't exist for UI purposes
        if not trace_detail["events"]:
            return None

        # Add empty snapshot placeholder
        trace_detail["snapshots"] = [{
            "kind": "initial",
            "timestamp": trace_detail["created_at"],
            "data": {},
        }]
        
        return trace_detail
    
    except Exception as e:
        logger.error(f"Error building trace detail for {trace_id}: {e}", exc_info=True)
        # Return minimal valid trace on error
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "status": "error",
            "error": str(e),
            "events": [],
        }


async def get_latest_nine_questions_report(
    request: Request,
    session_id: str,
) -> Optional[dict[str, Any]]:
    """
    Get the latest nine-questions report/trace for a session
    
    Args:
        request: FastAPI request
        session_id: Session ID
    
    Returns:
        Latest report data or None
    """
    facade = get_kernel_service_facade(request)
    
    try:
        # Get state manager and query latest state
        state_mgr = facade.get_nine_question_state_manager()
        
        if not state_mgr:
            return None
        
        state = await state_mgr.get_state(session_id)
        
        if not state:
            return None
        
        # Build report from state
        return {
            "session_id": session_id,
            "state_revision": getattr(state, "revision", 0),
            "questions_completed": getattr(state, "completed_questions", []),
            "timestamp": datetime.now().isoformat(),
            "trace_ids": getattr(state, "trace_ids", {}),
        }
    
    except Exception as e:
        logger.error(f"Error getting latest report for {session_id}: {e}")
        return None
