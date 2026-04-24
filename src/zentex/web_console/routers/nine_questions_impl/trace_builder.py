from __future__ import annotations
"""Trace Detail Builder

Constructs detailed trace information for nine-question execution traces.
Handles transcript query, event extraction, and formatting.
"""


import logging
from typing import Any, Optional
from datetime import datetime

from fastapi import HTTPException, Request

from zentex.web_console.dependencies import get_kernel_service_facade
from zentex.web_console.audit_event_serialization import serialize_audit_event

logger = logging.getLogger(__name__)


def _entry_type_value(entry: Any) -> str:
    entry_type = getattr(entry, "entry_type", None)
    return str(getattr(entry_type, "value", entry_type) or "")


def _extract_llm_trace_payload(entries: list[Any]) -> dict[str, Optional[Any]]:
    invoked_payload: dict[str, Any] = {}
    completed_payload: dict[str, Any] = {}
    failed_payload: dict[str, Any] = {}

    for entry in entries:
        entry_type = _entry_type_value(entry)
        payload = getattr(entry, "payload", None)
        if not isinstance(payload, dict):
            continue
        if entry_type == "model_provider_invoked":
            invoked_payload = payload
        elif entry_type == "model_provider_completed":
            completed_payload = payload
        elif entry_type == "model_provider_failed":
            failed_payload = payload

    if not invoked_payload and not completed_payload and not failed_payload:
        return None

    caller_context = invoked_payload.get("caller_context")
    caller_context = caller_context if isinstance(caller_context, dict) else {}
    token_usage = completed_payload.get("token_usage")
    token_usage = token_usage if isinstance(token_usage, dict) else {}

    return {
        "request_id": invoked_payload.get("request_id"),
        "decision_id": invoked_payload.get("decision_id"),
        "provider_name": invoked_payload.get("provider_name") or invoked_payload.get("provider_plugin_id"),
        "model": completed_payload.get("model") or failed_payload.get("model"),
        "system_prompt": invoked_payload.get("system_prompt"),
        "prompt": invoked_payload.get("prompt"),
        "source_module": caller_context.get("source_module"),
        "invocation_phase": caller_context.get("invocation_phase"),
        "question_driver_refs": caller_context.get("question_driver_refs") or [],
        "context_data": invoked_payload.get("context") if isinstance(invoked_payload.get("context"), dict) else {},
        "raw_response": completed_payload.get("raw_response") if isinstance(completed_payload.get("raw_response"), dict) else None,
        "token_usage": {
            "input_tokens": int(token_usage.get("input_tokens") or 0),
            "output_tokens": int(token_usage.get("output_tokens") or 0),
            "total_tokens": int(token_usage.get("total_tokens") or 0),
        },
        "elapsed_ms": completed_payload.get("elapsed_ms") or failed_payload.get("elapsed_ms"),
        "error_type": failed_payload.get("error_type"),
        "error_message": failed_payload.get("error_message") or failed_payload.get("error"),
    }


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
            "prompt": None,
            "context": {},
            "result": {},
            "invocation_phase": None,
            "source_module": None,
            "provider_plugin_id": None,
            "provider_name": None,
            "question_driver_refs": [],
            "invoked_at": None,
            "completed_at": None,
            "failed_at": None,
            "events": [],
            "related_events": [],
            "snapshots": [],
            "status": "completed",
        }
        
        entries: list[Any] = []
        transcript_query_failed = False
        transcript_query_error = ""
        audit_service = getattr(request.app.state, "audit_service", None)

        # Try to query audit service if available
        try:
            if audit_service is not None and callable(getattr(audit_service, "list_trace_events", None)):
                entries = list(audit_service.list_trace_events(trace_id) or [])

        except Exception as e:
            # Do not downgrade audit query failures into a fake "pending"
            # trace. That hides a real backend failure behind an empty placeholder
            # and makes the monitoring page lie about execution state.
            logger.exception("Could not query audit service for trace detail")
            transcript_query_failed = True
            transcript_query_error = str(e)

        for entry in entries:
            if all(hasattr(entry, attr) for attr in ("entry_id", "session_id", "turn_id", "entry_type", "timestamp", "source", "trace_id", "payload")):
                serialized = serialize_audit_event(entry, include_payload=True).model_dump()
                trace_detail["events"].append(serialized)
                trace_detail["related_events"].append(serialized)
            else:
                serialized = {
                    "entry_type": getattr(entry, "event_type", "unknown"),
                    "timestamp": str(getattr(entry, "timestamp", "")),
                    "payload": getattr(entry, "data", {}),
                }
                trace_detail["events"].append(serialized)
                trace_detail["related_events"].append(serialized)

        if not trace_detail["events"]:
            if transcript_query_failed:
                return {
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "status": "error",
                    "error_code": "trace_query_failed",
                    "error": transcript_query_error,
                    "events": [],
                    "snapshots": [],
                }
            # Do not fabricate a pending trace when there are no real audit events.
            # Returning a placeholder object here would fake that execution exists.
            return None

        llm_trace_payload = _extract_llm_trace_payload(entries)
        trace_detail["llm_trace_payload"] = llm_trace_payload
        if llm_trace_payload is not None:
            trace_detail["prompt"] = llm_trace_payload.get("prompt")
            trace_detail["context"] = llm_trace_payload.get("context_data") or {}
            trace_detail["source_module"] = llm_trace_payload.get("source_module")
            trace_detail["invocation_phase"] = llm_trace_payload.get("invocation_phase")
            trace_detail["provider_name"] = llm_trace_payload.get("provider_name")
            trace_detail["question_driver_refs"] = llm_trace_payload.get("question_driver_refs") or []

        for entry in entries:
            payload = getattr(entry, "payload", None)
            payload = payload if isinstance(payload, dict) else {}
            entry_type = _entry_type_value(entry)
            entry_timestamp = getattr(entry, "timestamp", None)
            timestamp_value = entry_timestamp.isoformat() if hasattr(entry_timestamp, "isoformat") else str(entry_timestamp or "")
            if entry_type == "model_provider_invoked":
                trace_detail["invoked_at"] = timestamp_value
                trace_detail["provider_plugin_id"] = payload.get("provider_plugin_id")
            elif entry_type == "model_provider_completed":
                trace_detail["completed_at"] = timestamp_value
                trace_detail["result"] = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            elif entry_type == "model_provider_failed":
                trace_detail["failed_at"] = timestamp_value

        # Only expose a synthetic snapshot after real events were found. Creating
        # placeholder snapshots for missing traces would fake that execution data
        # exists when it does not.
        trace_detail["snapshots"] = [{
            "kind": "initial",
            "timestamp": trace_detail["created_at"],
            "data": {},
        }]
        
        return trace_detail
    
    except Exception as e:
        logger.exception("Error building trace detail for %s", trace_id)
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "status": "error",
            "error_code": "trace_detail_build_failed",
            "error": str(e),
            "events": [],
        }


async def get_latest_nine_questions_report(
    request: Request,
) -> Optional[dict[str, Any]]:
    """Get the latest nine-questions report/trace for the shared baseline."""
    from zentex.web_console.routers.nine_questions_impl.q_state import (
        _get_nine_question_service,
    )
    try:
        nq_service = _get_nine_question_service(request)
        state = await nq_service.get_state()
        if not state:
            return None
        return {
            "state_revision": getattr(state, "revision", 0) if not isinstance(state, dict) else state.get("revision", 0),
            "questions_completed": getattr(state, "completed_questions", []) if not isinstance(state, dict) else state.get("completed_questions", []),
            "timestamp": datetime.now().isoformat(),
            "trace_ids": getattr(state, "trace_ids", {}) if not isinstance(state, dict) else state.get("trace_ids", {}),
        }
    except Exception as e:
        # Do not hide report assembly failures behind None. That makes the monitoring
        # page indistinguishable from "no report yet" while the backend is already
        # unhealthy.
        logger.exception("Error getting latest nine-questions report")
        return {
            "status": "degraded",
            "error_code": "nine_questions_report_unavailable",
            "exception_type": type(e).__name__,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
