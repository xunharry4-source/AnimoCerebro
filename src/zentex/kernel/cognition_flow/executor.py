from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""NineQuestionExecutor — runs individual nine-questions via the bridge."""

import copy
import time
import logging
from collections.abc import Callable
from zentex.kernel.cognition_flow.models import (
    NineQuestion,
    NineQuestionResponse,
)

logger = logging.getLogger(__name__)
from zentex.kernel.cognition_flow.state import NineQuestionStateManager
from zentex.kernel.state_domain import (
    TranscriptEntry,
    TranscriptEntryType,
    TranscriptStore,
)


class NineQuestionExecutor:
    """Executes nine-questions by delegating each to the bridge cognitive-plugin service.

    The *bridge* must provide:
        answer_nine_question(question: NineQuestion, context: dict) -> NineQuestionResponse
    """

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        questions: list[NineQuestion],
        context: dict,
        state_manager: NineQuestionStateManager,
        transcript: TranscriptStore,
        max_retries: int = 1,
        response_callback: Callable[[NineQuestionResponse], Optional[None]] = None,
    ) -> list[NineQuestionResponse]:
        """Execute *questions* sequentially and return all responses.
        
        Resilience features:
        - max_retries: Number of attempts per question on exception or error.
        - G6: Context Hygiene - only successful questions propagate state to downstream questions.
        - G8: Pure execution - results are returned as a batch for atomic commitment by the coordinator.
        """
        responses: list[NineQuestionResponse] = []
        session_id = state_manager.get_state().session_id
        rolling_context = dict(context)
        rolling_context.setdefault("context_snapshot", {})
        rolling_context.setdefault("nine_questions", {})

        for question in questions:
            # Step 1 — write cognitive-plugin inference transcript entry
            transcript.append(
                TranscriptEntry(
                    entry_type=TranscriptEntryType.nine_q_update,
                    session_id=session_id,
                    payload={
                        "question_id": question.question_id,
                        "plugin_id": question.plugin_id,
                        "phase": str("llm_inference"),
                        "text": question.text,
                    },
                )
            )

            # Execution loop with retry logic
            response: Optional[NineQuestionResponse] = None
            
            for attempt in range(max_retries + 1):
                if attempt > 0:
                    logger.warning(f"[RESILIENCE] Retrying Nine-Question Union[execution, ID]: {question.question_id} | Attempt: {attempt}/{max_retries}")
                    time.sleep(1.0)  # Simple 1s backoff

                start = time.perf_counter()
                try:
                    response = self._bridge.answer_nine_question(question, rolling_context)
                    duration_ms = (time.perf_counter() - start) * 1000.0
                    if not response.duration_ms:
                        response.duration_ms = duration_ms
                    
                    # G10: Only break retry if there is NO error. 
                    # Placeholder successes (masked errors) are now gone from the bridge.
                    if not response.error:
                        break
                except Exception as exc:  # noqa: BLE001
                    duration_ms = (time.perf_counter() - start) * 1000.0
                    response = NineQuestionResponse(
                        question_id=question.question_id,
                        answer="",
                        confidence=0.0,
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                    # If it's the last attempt, we keep this response
                    if attempt == max_retries:
                        break

            # G6: Context Hygiene - only propagate if the question succeeded
            if response and not response.error:
                # Update rolling context for downstream questions
                self._merge_response_into_context(rolling_context, response)
                
            if response:
                responses.append(response)
                if response_callback is not None:
                    response_callback(response)
                
                # Log outcome
                is_failed = bool(response.error)
                status_str = "success" if not is_failed else f"failed ({response.error})"
                logger.info(f"[COGNITIVE AUDIT] Nine-Question Union[finished, ID]: {question.question_id} | Status: {status_str}")

        return responses

    @staticmethod
    def _merge_response_into_context(context: dict[str, Any], response: NineQuestionResponse) -> None:
        """Propagate one question's durable outputs into later question inputs."""

        def _deep_merge(target: dict[str, Any], updates: dict[str, Any]) -> None:
            for key, value in updates.items():
                if isinstance(value, dict) and isinstance(target.get(key), dict):
                    _deep_merge(target[key], value)
                else:
                    target[key] = copy.deepcopy(value)

        updates = dict(response.context_updates or {})
        if not updates:
            return

        snapshot = context.setdefault("context_snapshot", {})
        if isinstance(snapshot, dict):
            snapshot_updates = {key: value for key, value in updates.items() if key != "nine_questions"}
            _deep_merge(snapshot, snapshot_updates)

        summaries = context.setdefault("nine_questions", {})
        if isinstance(summaries, dict):
            question_summaries = updates.get("nine_questions")
            if isinstance(question_summaries, dict):
                _deep_merge(summaries, question_summaries)
