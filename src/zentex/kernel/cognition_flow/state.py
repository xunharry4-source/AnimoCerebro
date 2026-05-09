"""NineQuestionStateManager — thread-safe nine-question session state."""

import copy
import logging
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from zentex.kernel.cognition_flow.models import (
    BootstrapStatus,
    NineQuestion,
    NineQuestionResponse,
    NineQuestionState,
)

UTC = timezone.utc
QUESTION_SUMMARY_KEYS = {
    "q1": "我在那",
    "q2": "我有什么",
    "q3": "我是谁",
    "q4": "我能做什么",
    "q5": "我不能干什么",
    "q6": "如果我做了会怎样 / 代价与后果是什么",
    "q7": "我还可以做什么",
    "q8": "我现在应该做什么",
    "q9": "我应该如何行动",
}


def _isolate_question_payload(question_id: str, payload: dict) -> dict:
    isolated = _safe_deepcopy(payload)
    own_summary_key = QUESTION_SUMMARY_KEYS.get(question_id)

    if own_summary_key and isinstance(isolated.get("nine_questions"), dict):
        own_value = isolated["nine_questions"].get(own_summary_key)
        isolated["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}

    nested_context_updates = isolated.get("context_updates")
    if own_summary_key and isinstance(nested_context_updates, dict):
        nested_summaries = nested_context_updates.get("nine_questions")
        if isinstance(nested_summaries, dict):
            own_value = nested_summaries.get(own_summary_key)
            nested_context_updates["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}

    return isolated


def _safe_deepcopy(value: Any) -> Any:
    if isinstance(value, dict):
        items: list[tuple[Any, Any]] | None = None
        for _ in range(3):
            try:
                items = list(value.items())
                break
            except RuntimeError:
                # Concurrent mutation can happen while collecting snapshot data.
                continue
        if items is None:
            keys = list(value.keys())
            items = [(k, value.get(k)) for k in keys]
        return {k: _safe_deepcopy(v) for k, v in items}

    if isinstance(value, list):
        return [_safe_deepcopy(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_safe_deepcopy(item) for item in value)
    if isinstance(value, set):
        return {_safe_deepcopy(item) for item in value}

    try:
        return copy.deepcopy(value)
    except RuntimeError:
        return value


class NineQuestionStateManager:
    """Thread-safe manager for the nine-question bootstrap state of one session."""

    def __init__(self, session_id: str) -> None:
        self._state = NineQuestionState(session_id=session_id, responses={})
        self._lock = threading.RLock()
        # Batch H: Forensic Tracking
        self._pollution_violations: list[str] = []

    def get_pollution_metrics(self) -> dict[str, Any]:
        """Return a summary of pollution guard hits for this session (G38 Forensic Digest)."""
        with self._lock:
            return {
                "total_violations": len(self._pollution_violations),
                "violation_types": list(set(self._pollution_violations)),
                "details": self._pollution_violations[:10]  # Limit to first 10 for log brevity
            }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_response(self, response: NineQuestionResponse, merge_partial: bool = False) -> None:
        """Thread-safe update of a single question response.
        
        If merge_partial is True, result_payload and context_updates will be deep-merged
        with the existing response if one exists.
        """
        with self._lock:
            if merge_partial and response.question_id in self._state.responses:
                existing = self._state.responses[response.question_id]
                self._merge_responses(existing, response)
                self._state.responses[response.question_id] = existing
            else:
                # Sanitize initial payloads (Batch G)
                sanitized_context = {}
                self._deep_merge_dicts(sanitized_context, response.context_updates or {})
                response.context_updates = sanitized_context
                
                sanitized_result = {}
                self._deep_merge_dicts(sanitized_result, response.result_payload or {})
                response.result_payload = sanitized_result
                
                self._state.responses[response.question_id] = response
                
            self._state.last_updated_at = datetime.now(UTC).isoformat()

    def _merge_responses(self, target: NineQuestionResponse, source: NineQuestionResponse) -> None:
        """Deep merge source response data into target response."""
        # Update scalar fields
        target.answer = source.answer or target.answer
        target.confidence = source.confidence if source.confidence > 0 else target.confidence
        target.error = source.error
        target.duration_ms = source.duration_ms
        target.timestamp = source.timestamp or target.timestamp
        target.trace_id = source.trace_id or target.trace_id
        
        # Deep merge specific payloads
        self._deep_merge_dicts(target.result_payload, source.result_payload)
        self._deep_merge_dicts(target.context_updates, source.context_updates)
        self._deep_merge_dicts(target.execution_context, source.execution_context)
        self._deep_merge_dicts(target.execution_result, source.execution_result)
        self._deep_merge_dicts(target.llm_trace_payload, source.llm_trace_payload)
        
        # Update metadata
        target.is_partial = False  # The resulting merged response is considered "Current"
        target.success_modules = list(set(target.success_modules + source.success_modules))
        target.failed_modules = source.failed_modules  # Only keep current failures

    MAX_DEPTH = 5
    MAX_TOTAL_KEYS = 500

    def _deep_merge_dicts(self, target: dict[str, Any], updates: dict[str, Any], depth: int = 0) -> None:
        """Propagate one question's durable outputs into later question inputs (Harden with Batch G guards)."""
        if depth > self.MAX_DEPTH:
            msg = f"Max depth ({self.MAX_DEPTH}) exceeded"
            logger.warning(f"Cognition Pollution Guard: {msg} during merge. Truncating.")
            with self._lock:
                self._pollution_violations.append(msg)
            return

        for key, value in updates.items():
            # 1. Total key breadth limit check
            if len(target) >= self.MAX_TOTAL_KEYS and key not in target:
                msg = f"Max total keys ({self.MAX_TOTAL_KEYS}) reached"
                logger.warning(f"Cognition Pollution Guard: {msg}. Skipping key: {key}")
                with self._lock:
                    self._pollution_violations.append(msg)
                continue

            # 2. Type and Structure Validation
            if isinstance(value, dict):
                if not isinstance(target.get(key), dict):
                    target[key] = {}
                self._deep_merge_dicts(target[key], value, depth + 1)
            elif isinstance(value, (str, int, float, bool, list, type(None))):
                # Basic primitives and lists are allowed
                target[key] = copy.deepcopy(value)
            else:
                # Reject functions, class instances, etc.
                msg = f"Rejected invalid value type: {type(value)}"
                logger.warning(f"Cognition Pollution Guard: {msg} for key '{key}'")
                with self._lock:
                    self._pollution_violations.append(msg)
                continue

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
            question_snapshots = {
                qid: {
                    "tool_id": r.tool_id or f"nine_questions.{qid}",
                    "summary": r.answer,
                    "confidence": r.confidence,
                    "result": _isolate_question_payload(qid, r.result_payload) if r.result_payload else responses_dict[qid],
                    "llm_output": _safe_deepcopy(r.result_payload.get("llm_output")) if isinstance(r.result_payload, dict) and isinstance(r.result_payload.get("llm_output"), dict) else {},
                    "context_updates": _isolate_question_payload(qid, r.context_updates) if r.context_updates else {},
                    "execution_context": _safe_deepcopy(r.execution_context) if r.execution_context else {},
                    "execution_result": _safe_deepcopy(r.execution_result) if r.execution_result else {},
                    "llm_trace_payload": _safe_deepcopy(r.llm_trace_payload) if r.llm_trace_payload else {},
                    "trace_id": r.trace_id or f"{qid}:no-trace",
                    "timestamp": r.timestamp or self._state.last_updated_at,
                }
                for qid, r in self._state.responses.items()
            }
            return {
                "session_id": self._state.session_id,
                "bootstrap_status": self._state.bootstrap_status.value,
                "last_updated_at": self._state.last_updated_at,
                "responses": responses_dict,
                "question_snapshots": question_snapshots,
            }
