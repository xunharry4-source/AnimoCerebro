from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional

from zentex.runtime.nine_questions.state import NineQuestionId, NineQuestionState


NineQuestionEventType = Literal[
    "cold_start",
    "manual_intervention",
    "agent_connected",
    "environment_major_change",
]


@dataclass(frozen=True)
class NineQuestionEvent:
    event_type: NineQuestionEventType
    reason: str
    trace_id: str
    created_at: datetime
    dirty_questions: List[NineQuestionId]
    payload: Dict[str, Any]


def build_event(
    *,
    event_type: NineQuestionEventType,
    reason: str,
    trace_id: str,
    dirty_questions: List[NineQuestionId],
    payload: Dict[str, Any] | None = None,
) -> NineQuestionEvent:
    return NineQuestionEvent(
        event_type=event_type,
        reason=reason,
        trace_id=trace_id,
        created_at=datetime.now(timezone.utc),
        dirty_questions=list(dirty_questions),
        payload=dict(payload or {}),
    )


class NineQuestionRouter:
    """
    Event-driven router for independent nine-question recomputation.

    The router only decides dirty flags and delegates actual computation to an
    injected executor callback. This enforces the red line:
    - hot paths may publish events and mark dirty, but do not run inference
    - inference runs in an explicit executor call (can be queued)
    """

    def __init__(self) -> None:
        self._queue: List[NineQuestionEvent] = []

    def publish(self, state: NineQuestionState, event: NineQuestionEvent) -> None:
        state.mark_dirty(event.dirty_questions, reason=event.reason)
        self._queue.append(event)

    def drain(self) -> List[NineQuestionEvent]:
        events = list(self._queue)
        self._queue.clear()
        return events

    @staticmethod
    def derive_dirty_questions_for_event(
        event_type: NineQuestionEventType,
        *,
        action: Optional[str] = None,
    ) -> List[NineQuestionId]:
        if event_type == "cold_start":
            return ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"]
        if event_type == "agent_connected":
            return ["q3", "q4", "q5"]
        if event_type == "environment_major_change":
            return ["q1", "q2", "q3"]
        if event_type == "manual_intervention":
            normalized = str(action or "")
            if normalized == "role_change":
                return ["q2"]
            if normalized in {"reject_action", "pause"}:
                return ["q8", "q9"]
            return ["q2"]
        return ["q1", "q2", "q3"]
