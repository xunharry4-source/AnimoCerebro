"""Nine-Question Specific Handlers

Handles execution and testing logic for individual questions (Q1-Q9).
Delegates to question-specific services (evidence_q1-q9) as needed.

This module orchestrates the flow:
  1. Request → run_question_test() / execute_all_nine_questions()
  2. Calls _extract_qX_preprocessed_evidence(context) for evidence building
  3. Calls _extract_qX_inference_result(result) for result extraction
  4. Returns structured response
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request

from zentex.web_console.contracts.nine_questions import (
    NineQuestionsRunResponse,
    NineQuestionReportItem,
)
from zentex.web_console.dependencies import get_kernel_service_facade

# Import evidence extractors for Q1-Q9
from .evidence_q1 import (
    _extract_q1_preprocessed_evidence,
    _extract_q1_inference_result,
)
from .evidence_q2 import (
    _extract_q2_preprocessed_evidence,
    _extract_q2_inference_result,
)
from .evidence_q3 import (
    _extract_q3_preprocessed_evidence,
    _extract_q3_inference_result,
)
from .evidence_q4 import (
    _extract_q4_preprocessed_evidence,
    _extract_q4_inference_result,
)
from .evidence_q5 import (
    _extract_q5_preprocessed_evidence,
    _extract_q5_inference_result,
)
from .evidence_q6 import (
    _extract_q6_preprocessed_evidence,
    _extract_q6_inference_result,
)
from .evidence_q7 import (
    _extract_q7_preprocessed_evidence,
    _extract_q7_inference_result,
)
from .evidence_q8 import (
    _extract_q8_preprocessed_evidence,
    _extract_q8_inference_result,
)
from .evidence_q9 import (
    _extract_q9_preprocessed_evidence,
    _extract_q9_inference_result,
)

logger = logging.getLogger(__name__)


# ========== Q Handler Registry ==========
# Maps question_id (q1-q9) to their evidence extraction functions

QUESTION_HANDLERS = {
    "q1": {
        "evidence": _extract_q1_preprocessed_evidence,
        "result": _extract_q1_inference_result,
        "title": "我在哪",
    },
    "q2": {
        "evidence": _extract_q2_preprocessed_evidence,
        "result": _extract_q2_inference_result,
        "title": "我是谁",
    },
    "q3": {
        "evidence": _extract_q3_preprocessed_evidence,
        "result": _extract_q3_inference_result,
        "title": "我有什么",
    },
    "q4": {
        "evidence": _extract_q4_preprocessed_evidence,
        "result": _extract_q4_inference_result,
        "title": "我能做什么",
    },
    "q5": {
        "evidence": _extract_q5_preprocessed_evidence,
        "result": _extract_q5_inference_result,
        "title": "我被允许做什么",
    },
    "q6": {
        "evidence": _extract_q6_preprocessed_evidence,
        "result": _extract_q6_inference_result,
        "title": "我即使能做也不该做什么",
    },
    "q7": {
        "evidence": _extract_q7_preprocessed_evidence,
        "result": _extract_q7_inference_result,
        "title": "我还可以做什么",
    },
    "q8": {
        "evidence": _extract_q8_preprocessed_evidence,
        "result": _extract_q8_inference_result,
        "title": "我现在应该做什么",
    },
    "q9": {
        "evidence": _extract_q9_preprocessed_evidence,
        "result": _extract_q9_inference_result,
        "title": "我应该如何行动",
    },
}


# ========== Individual Question Handlers ==========

async def _process_question_evidence(
    request: Request,
    question_id: str,
    context_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Process a single question's evidence building
    
    Args:
        request: FastAPI request
        question_id: Which question (q1-q9)
        context_payload: Context snapshot from kernel
    
    Returns:
        Preprocessed evidence as dict
    """
    if question_id not in QUESTION_HANDLERS:
        raise HTTPException(status_code=400, detail=f"Unknown question: {question_id}")
    
    handler = QUESTION_HANDLERS[question_id]
    try:
        evidence = handler["evidence"](context_payload)
        return evidence.model_dump() if hasattr(evidence, "model_dump") else evidence
    except Exception as e:
        logger.error(f"Evidence processing error for {question_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Evidence processing failed for {question_id}")


async def _process_question_result(
    request: Request,
    question_id: str,
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Extract inference result from a question's processing
    
    Args:
        request: FastAPI request
        question_id: Which question (q1-q9)
        result_payload: Result from tool/LLM execution
    
    Returns:
        Extracted inference result as dict
    """
    if question_id not in QUESTION_HANDLERS:
        raise HTTPException(status_code=400, detail=f"Unknown question: {question_id}")
    
    handler = QUESTION_HANDLERS[question_id]
    try:
        inference = handler["result"](result_payload)
        return inference.model_dump() if hasattr(inference, "model_dump") else inference
    except Exception as e:
        logger.error(f"Result extraction error for {question_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Result extraction failed for {question_id}")


# ========== Public API: test/execution ==========

async def run_question_test(
    request: Request,
    question_id: str,
    session_id: str,
    state: NineQuestionState,
    test_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Run sandbox test for a specific question
    
    Executes evidence building + result extraction for a given question
    in the context of the current session state.
    
    Args:
        request: FastAPI request
        question_id: Which question to test (q1-q9)
        session_id: Session context
        state: Current nine-question state
        test_payload: Test input data (context snapshot, mock result, etc.)
    
    Returns:
        Test execution result containing evidence and inference
    """
    if question_id not in QUESTION_HANDLERS:
        raise HTTPException(status_code=400, detail=f"Unknown question: {question_id}")
    
    facade = get_kernel_service_facade(request)
    handler_info = QUESTION_HANDLERS[question_id]
    
    try:
        # Extract test components from payload
        context_snapshot = test_payload.get("context", {})
        result_payload = test_payload.get("result", {})
        
        # Process evidence
        evidence = await _process_question_evidence(request, question_id, context_snapshot)
        
        # Process result
        inference = await _process_question_result(request, question_id, result_payload)
        
        # Build trace metadata
        trace_id = str(uuid4())
        event_bus = facade.get_event_bus()
        
        # Publish test event
        await event_bus.publish(
            event_type=f"nine_question_test_executed",
            payload={
                "question_id": question_id,
                "session_id": session_id,
                "trace_id": trace_id,
                "status": "success",
            }
        )
        
        return {
            "question_id": question_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "status": "success",
            "title": handler_info["title"],
            "evidence": evidence,
            "inference": inference,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test execution error for {question_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Test execution failed for {question_id}")


async def execute_all_nine_questions(
    request: Request,
    session_id: str,
    state: NineQuestionState,
) -> NineQuestionsRunResponse:
    """Execute all nine questions Q1→Q9 via the kernel bootstrap.

    Delegates to ``facade.ensure_nine_questions_bootstrap(force=True)`` which
    runs in a thread-pool executor so the event loop is never blocked.  After
    execution the state is persisted and Q8 tasks are synced to task_service.
    """
    import asyncio

    from .q_commons import (
        get_nine_question_state,
        get_question_snapshot_map,
        _persist_kernel_nine_question_state,
    )

    facade = get_kernel_service_facade(request)
    main_trace_id = str(uuid4())

    try:
        # Run the blocking bootstrap off the event loop with a hard 90-second cap.
        # force=True so that an already-completed session can be fully re-run.
        await asyncio.wait_for(
            asyncio.to_thread(
                facade.ensure_nine_questions_bootstrap, session_id, force=True
            ),
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
        raise HTTPException(
            status_code=503,
            detail=f"Kernel session unavailable for nine-question bootstrap: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Nine questions bootstrap failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Nine questions execution failed")

    # Force-sync kernel's fresh in-memory state into the persistent store.
    fresh_kernel_state = facade.get_nine_question_state(session_id)
    if fresh_kernel_state and get_question_snapshot_map(fresh_kernel_state):
        await _persist_kernel_nine_question_state(request, session_id, fresh_kernel_state)

    updated_state = await get_nine_question_state(request, session_id)
    snapshot_map = get_question_snapshot_map(updated_state)

    # Sync Q8 results to task_service (same as the HTTP route handler does).
    try:
        from .route_handlers import _sync_q8_tasks_to_task_service
        await _sync_q8_tasks_to_task_service(request, session_id, snapshot_map)
    except Exception as exc:
        logger.error(
            "Q8 task sync failed after execute_all_nine_questions for session %s: %s",
            session_id,
            exc,
            exc_info=True,
        )

    snapshot_version = int(
        updated_state.get("snapshot_version", len(snapshot_map))
        if isinstance(updated_state, dict)
        else getattr(updated_state, "snapshot_version", len(snapshot_map))
    )
    revision = int(
        updated_state.get("revision", 0)
        if isinstance(updated_state, dict)
        else getattr(updated_state, "revision", 0)
    )
    return NineQuestionsRunResponse(
        started=bool(snapshot_map),
        trace_id=main_trace_id,
        refresh_reason="all_nine_questions_executed",
        snapshot_version=snapshot_version,
        revision=revision,
    )
