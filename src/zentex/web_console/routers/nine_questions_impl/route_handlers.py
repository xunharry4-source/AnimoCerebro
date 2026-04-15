"""Nine Questions API Route Handler v2 - Refactored with Facade-First Design

⚠️  MODULARIZATION CONSTRAINT - MAX 800 LINES
════════════════════════════════════════════════════════════════════
This module MUST NOT exceed 800 lines. All business logic extracted to:
  - q_commons.py: Shared nine-question logic
  - trace_builder.py: Trace construction & formatting
  - q1, q2, ..., q9 services in handlers/ subdirectory

This file contains ONLY route definitions that delegate to services.
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from zentex.web_console.dependencies import (
    get_kernel_service_facade,
    get_session_manager,
    get_nine_question_state_manager,
    get_event_bus,
    get_runtime,
)
from zentex.web_console.contracts.nine_questions import (
    NineQuestionsRunRequest,
    NineQuestionsRunResponse,
    NineQuestionsReportPayload,
    NineQuestionReportItem,
)

# Import service layer
from .q_commons import (
    get_or_create_session,
    get_nine_question_state,
    build_question_report_items,
    get_question_snapshot_map,
)
from .trace_builder import build_trace_detail

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== Constants ==========

QUESTION_TITLES = {
    "q1": "我在哪",
    "q2": "我是谁",
    "q3": "我有什么",
    "q4": "我能做什么",
    "q5": "我被允许做什么",
    "q6": "我即使能做也不该做什么",
    "q7": "我还可以做什么",
    "q8": "我现在应该做什么",
    "q9": "我应该如何行动",
}


def _stringify_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


# ========== Route Definitions (Facade-First) ==========

@router.get("/nine-questions/status", response_model=NineQuestionsReportPayload)
async def get_nine_questions_status(request: Request):
    """Get lightweight nine-question status (metadata only, no heavy trace details)"""
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)
    
    questions = await build_question_report_items(
        request=request,
        state=state,
        include_trace_detail=False,  # Lightweight - no trace construction
    )
    
    return NineQuestionsReportPayload(
        session_id=session.session_id,
        last_turn_id=str(getattr(session, "last_turn_id", "") or ""),
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=_stringify_timestamp(state.get("last_updated_at") if isinstance(state, dict) else getattr(state, "updated_at", None)),
        last_refresh_reason=(state.get("last_refresh_reason") if isinstance(state, dict) else getattr(state, "last_refresh_reason", None)),
        question_driver_refs=list(state.get("question_driver_refs", []) if isinstance(state, dict) else getattr(state, "question_driver_refs", [])),
        questions=questions,
        trace_ids={qid: str(item.get("trace_id") or "") for qid, item in get_question_snapshot_map(state).items()},
    )


@router.get("/nine-questions/latest-report", response_model=NineQuestionsReportPayload)
async def get_latest_nine_questions_report(request: Request):
    """Get latest nine-questions report with full details"""
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)
    
    questions = await build_question_report_items(
        request=request,
        state=state,
        include_trace_detail=True,  # Full report - include traces
    )
    
    return NineQuestionsReportPayload(
        session_id=session.session_id,
        last_turn_id=str(getattr(session, "last_turn_id", "") or ""),
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=_stringify_timestamp(state.get("last_updated_at") if isinstance(state, dict) else getattr(state, "updated_at", None)),
        last_refresh_reason=(state.get("last_refresh_reason") if isinstance(state, dict) else getattr(state, "last_refresh_reason", None)),
        question_driver_refs=list(state.get("question_driver_refs", []) if isinstance(state, dict) else getattr(state, "question_driver_refs", [])),
        questions=questions,
        trace_ids={qid: str(item.get("trace_id") or "") for qid, item in get_question_snapshot_map(state).items()},
    )


@router.get("/nine-questions/{question_id}")
async def get_nine_question_detail(request: Request, question_id: str):
    """Get detailed information for a specific question"""
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)
    
    snapshot = get_question_snapshot_map(state).get(question_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Question {question_id} has no snapshot")
    
    # Build single question item with full trace detail
    question_item = await build_question_report_items(
        request=request,
        state=state,
        question_filter=question_id,
        include_trace_detail=True,
    )
    
    return question_item[0] if question_item else None


@router.get("/nine-questions/traces/{trace_id}")
async def get_nine_question_trace_detail(request: Request, trace_id: str):
    """Get detailed trace information for a specific question execution"""
    session = await get_or_create_session(request)
    
    # Build trace detail
    trace_detail = await build_trace_detail(
        request=request,
        trace_id=trace_id,
        session_id=session.session_id,
    )
    
    if not trace_detail:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    
    return trace_detail


@router.post("/nine-questions/{question_id}/test")
async def run_nine_question_sandbox_test(
    request: Request,
    question_id: str,
    test_request: dict[str, Any],
):
    """Run sandbox test for a specific question with test payload"""
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)
    
    # Delegate to question-specific test handler
    from .q_handlers import run_question_test
    result = await run_question_test(
        request=request,
        question_id=question_id,
        session_id=session.session_id,
        state=state,
        test_payload=test_request,
    )
    
    return result


@router.post("/nine-questions/run-all")
async def run_all_nine_questions(
    request: Request,
    run_request: NineQuestionsRunRequest,
) -> NineQuestionsRunResponse:
    """Execute all nine questions end-to-end.

    IMPORTANT: ensure_nine_questions_bootstrap() is a synchronous, potentially
    long-running call (up to 9 × LLM RTT).  It MUST run in a thread-pool
    executor via asyncio.to_thread() to avoid blocking uvicorn's event loop and
    starving other in-flight requests.  Failure to do so causes the worker to
    become unresponsive and eventually crash under load or when a client times
    out and closes the TCP connection mid-call.
    """
    import asyncio

    session = await get_or_create_session(request)
    runtime = get_runtime(request)

    try:
        # Run the blocking bootstrap off the event loop with a hard 90-second cap.
        await asyncio.wait_for(
            asyncio.to_thread(runtime.ensure_nine_questions_bootstrap, session.session_id),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "nine_question_bootstrap_timeout",
                "message": "九问引导超时（90s），请稍后重试。",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Kernel session unavailable for nine-question bootstrap: {exc}") from exc

    state = await get_nine_question_state(request, session.session_id)
    snapshot_map = get_question_snapshot_map(state)

    return NineQuestionsRunResponse(
        started=bool(snapshot_map),
        trace_id=str(session.session_id),
        refresh_reason="all_nine_questions_executed",
        snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
    )
