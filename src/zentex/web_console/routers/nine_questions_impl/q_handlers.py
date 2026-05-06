from __future__ import annotations
"""Nine-Question Specific Handlers

Handles execution and testing logic for individual questions (Q1-Q9).
Delegates to question-specific services (evidence_q1-q9) as needed.

This module orchestrates the flow:
  1. Request → run_question_test() / execute_all_nine_questions()
  2. Calls _extract_qX_preprocessed_evidence(context) for evidence building
  3. Calls _extract_qX_inference_result(result) for result extraction
  4. Returns structured response
"""


import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request

from zentex.web_console.contracts.nine_questions import (
    NineQuestionsRunResponse,
    NineQuestionReportItem,
)
from zentex.nine_questions.question_driver_framework import (
    ensure_mounted_plugins,
    ensure_question_driver_trace,
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
        "title": "我在那",
    },
    "q2": {
        "evidence": _extract_q2_preprocessed_evidence,
        "result": _extract_q2_inference_result,
        "title": "我有什么",
    },
    "q3": {
        "evidence": _extract_q3_preprocessed_evidence,
        "result": _extract_q3_inference_result,
        "title": "我是谁",
    },
    "q4": {
        "evidence": _extract_q4_preprocessed_evidence,
        "result": _extract_q4_inference_result,
        "title": "我能干什么",
    },
    "q5": {
        "evidence": _extract_q5_preprocessed_evidence,
        "result": _extract_q5_inference_result,
        "title": "我可以干什么",
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
        "title": "我应该干什么",
    },
    "q9": {
        "evidence": _extract_q9_preprocessed_evidence,
        "result": _extract_q9_inference_result,
        "title": "我应该怎么做",
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
        logger.error(f"Evidence processing error for {question_id}: {e}", exc_info=True)
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
        logger.error(f"Result extraction error for {question_id}: {e}", exc_info=True)
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
    
    handler_info = QUESTION_HANDLERS[question_id]
    started_at = time.monotonic()
    
    try:
        # Extract test components from payload
        context_snapshot = test_payload.get("mock_context") or test_payload.get("context") or {}
        result_payload = test_payload.get("mock_result") or test_payload.get("result") or {}
        if not isinstance(context_snapshot, dict):
            raise HTTPException(status_code=400, detail="Sandbox context must be a JSON object")
        if not isinstance(result_payload, dict):
            raise HTTPException(status_code=400, detail="Sandbox result must be a JSON object")
        
        # Process evidence
        evidence = await _process_question_evidence(request, question_id, context_snapshot)
        
        # Process result
        inference = await _process_question_result(request, question_id, result_payload)
        
        # Build trace metadata
        trace_id = f"sandbox:{question_id}:{uuid4()}"
        llm_trace_payload = ensure_question_driver_trace(
            question_id,
            test_payload.get("llm_trace_payload") if isinstance(test_payload.get("llm_trace_payload"), dict) else {},
            context_data=context_snapshot,
            raw_response=result_payload,
            sandbox=True,
        )
        
        return {
            "question_id": question_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "tool_id": f"nine_questions.{question_id}",
            "status": "success",
            "title": handler_info["title"],
            "summary": f"Sandbox projection for {question_id}",
            "confidence": float(result_payload.get("confidence") or 0.0),
            "elapsed_ms": int((time.monotonic() - started_at) * 1000),
            "provider_name": llm_trace_payload.get("provider_name"),
            "mounted_plugins": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in ensure_mounted_plugins(question_id, [])
            ],
            "prompt": llm_trace_payload.get("prompt"),
            "context": context_snapshot,
            "result": result_payload,
            "context_updates": {},
            "evidence": evidence,
            "inference": inference,
            "preprocessed_evidence": evidence,
            "inference_result": inference,
            "llm_trace_payload": llm_trace_payload,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test execution error for {question_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Test execution failed for {question_id}: {e}")


async def execute_all_nine_questions(
    request: Request,
    session_id: str,
    state: NineQuestionState,
) -> NineQuestionsRunResponse:
    """
    Execute all nine questions end-to-end
    
    Orchestrates the complete nine-question reasoning chain:
    Q1 → Q2 → ... → Q9
    
    Args:
        request: FastAPI request
        session_id: Session ID
        state: Current nine-question state
    
    Returns:
        Execution result with status and trace IDs
    """
    facade = get_kernel_service_facade(request)
    event_bus = facade.get_event_bus()
    main_trace_id = str(uuid4())
    
    try:
        trace_ids = {}
        question_results = {}
        
        # Execute each question in sequence
        for question_id in ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"]:
            try:
                logger.info(f"Executing {question_id}...")
                
                # Prepare test payload with empty context/result for now
                # In production, this would be populated from kernel state
                test_payload = {
                    "context": {},
                    "result": {},
                }
                
                # Run question test
                result = await run_question_test(
                    request=request,
                    question_id=question_id,
                    session_id=session_id,
                    state=state,
                    test_payload=test_payload,
                )
                
                trace_id = result.get("trace_id", str(uuid4()))
                trace_ids[question_id] = trace_id
                question_results[question_id] = {
                    "status": result.get("status", "success"),
                    "trace_id": trace_id,
                }
                
            except Exception as e:
                logger.error(f"Error executing {question_id}: {e}", exc_info=True)
                trace_id = str(uuid4())
                trace_ids[question_id] = trace_id
                question_results[question_id] = {
                    "status": "error",
                    "trace_id": trace_id,
                    "error": str(e),
                }
        
        # Publish completion event
        await event_bus.publish(
            event_type="nine_questions_execution_completed",
            payload={
                "session_id": session_id,
                "trace_id": main_trace_id,
                "question_results": question_results,
            }
        )
        
        return NineQuestionsRunResponse(
            started=True,
            trace_id=main_trace_id,
            refresh_reason="all_nine_questions_executed",
            snapshot_version=1,
            revision=state.revision if state else 0,
        )
    
    except Exception as e:
        logger.error(f"Nine questions execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Nine questions execution failed")
