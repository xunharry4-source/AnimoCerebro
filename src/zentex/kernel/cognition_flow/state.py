"""NineQuestionStateManager — thread-safe nine-question session state."""

import copy
import threading
from datetime import datetime, timezone

from zentex.kernel.cognition_flow.models import (
    BootstrapStatus,
    NineQuestion,
    NineQuestionResponse,
    NineQuestionState,
)

UTC = timezone.utc


class NineQuestionStateManager:
    """Thread-safe manager for the nine-question bootstrap state of one session."""

    def __init__(self, session_id: str) -> None:
        self._state = NineQuestionState(session_id=session_id, responses={})
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_response(self, response: NineQuestionResponse) -> None:
        """Thread-safe update of a single question response."""
        with self._lock:
            self._state.responses[response.question_id] = response
            self._state.last_updated_at = datetime.now(UTC).isoformat()

    def set_bootstrap_status(self, status: BootstrapStatus) -> None:
        """Update the overall bootstrap status."""
        with self._lock:
            self._state.bootstrap_status = status
            self._state.last_updated_at = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_state(self) -> NineQuestionState:
        """Return a shallow copy of the current state."""
        with self._lock:
            return NineQuestionState(
                session_id=self._state.session_id,
                responses=dict(self._state.responses),
                bootstrap_status=self._state.bootstrap_status,
                last_updated_at=self._state.last_updated_at,
            )

    def is_question_answered(self, question_id: str) -> bool:
        """Return True if *question_id* has a non-empty answer and no error."""
        with self._lock:
            resp = self._state.responses.get(question_id)
        if resp is None:
            return False
        return bool(resp.answer) and not resp.error

    def unanswered_questions(self, questions: list[NineQuestion]) -> list[NineQuestion]:
        """Return the subset of *questions* that do not yet have a valid answer."""
        return [q for q in questions if not self.is_question_answered(q.question_id)]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a plain-dict representation of the current state."""
        with self._lock:
            responses_dict = {
                qid: {
                    "question_id": r.question_id,
                    "answer": r.answer,
                    "confidence": r.confidence,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for qid, r in self._state.responses.items()
            }
            return {
                "session_id": self._state.session_id,
                "bootstrap_status": str(self._state.bootstrap_status),
                "last_updated_at": self._state.last_updated_at,
                "responses": responses_dict,
            }
