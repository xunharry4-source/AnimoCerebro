"""NineQuestionExecutor — runs individual nine-questions via the bridge."""

import time
from typing import Any

from zentex.kernel.cognition_flow.models import (
    NineQuestion,
    NineQuestionResponse,
)
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
    ) -> list[NineQuestionResponse]:
        """Execute *questions* sequentially and return all responses.

        Each question:
        1. Writes a transcript entry marking the start of cognitive-plugin inference.
        2. Calls bridge.answer_nine_question(question, context).
        3. On success: updates state_manager and writes a state_write entry.
        4. On failure: records an error response and continues.

        Args:
            questions:     Ordered list of NineQuestion objects to execute.
            context:       Snapshot context dict provided to every question.
            state_manager: Mutable state manager for this session.
            transcript:    Transcript store for this session.

        Returns:
            List of NineQuestionResponse (one per question, success or error).
        """
        responses: list[NineQuestionResponse] = []
        session_id = state_manager.get_state().session_id

        for question in questions:
            # Step 1 — write cognitive-plugin inference transcript entry
            transcript.append(
                TranscriptEntry(
                    entry_type=TranscriptEntryType.nine_q_update,
                    session_id=session_id,
                    payload={
                        "question_id": question.question_id,
                        "plugin_id": question.plugin_id,
                        "phase": str(
                            "llm_inference"
                        ),
                        "text": question.text,
                    },
                )
            )

            # Step 2 — call bridge
            start = time.perf_counter()
            try:
                response: NineQuestionResponse = self._bridge.answer_nine_question(
                    question, context
                )
                duration_ms = (time.perf_counter() - start) * 1000.0
                # Ensure duration is set (bridge may not fill it)
                if not response.duration_ms:
                    response.duration_ms = duration_ms

                # Step 3a — update state
                state_manager.update_response(response)

                # Step 3b — write state_write transcript entry
                transcript.append(
                    TranscriptEntry(
                        entry_type=TranscriptEntryType.nine_q_update,
                        session_id=session_id,
                        payload={
                            "question_id": question.question_id,
                            "plugin_id": question.plugin_id,
                            "phase": "state_write",
                            "confidence": response.confidence,
                            "has_answer": bool(response.answer),
                        },
                    )
                )

            except Exception as exc:  # noqa: BLE001
                duration_ms = (time.perf_counter() - start) * 1000.0
                response = NineQuestionResponse(
                    question_id=question.question_id,
                    answer="",
                    confidence=0.0,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                state_manager.update_response(response)

                transcript.append(
                    TranscriptEntry(
                        entry_type=TranscriptEntryType.nine_q_update,
                        session_id=session_id,
                        payload={
                            "question_id": question.question_id,
                            "plugin_id": question.plugin_id,
                            "phase": "state_write",
                            "error": str(exc),
                        },
                    )
                )

            responses.append(response)

        return responses
