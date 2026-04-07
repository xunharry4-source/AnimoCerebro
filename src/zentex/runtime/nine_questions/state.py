from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional


NineQuestionId = Literal["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NineQuestionState:
    """
    Session-local nine-question snapshot cache with dirty-flag routing.

    Red lines enforced by design:
    - Hot paths only read this object; no inference happens here.
    - Any inference must go through the router/executor and persist updates into transcript.
    """

    snapshot_version: int = 0
    revision: int = 0
    last_refresh_reason: str = "bootstrap"
    refreshed_at: datetime = field(default_factory=_now)
    question_driver_refs: List[str] = field(default_factory=list)

    # Compatibility fields (used by web-console replay + intervention receipt payloads).
    current_role_hypothesis: Optional[str] = None
    current_context: Dict[str, Any] = field(default_factory=dict)
    active_constraints: List[Any] = field(default_factory=list)
    operator_patch: Dict[str, Any] = field(default_factory=dict)

    # Dirty routing + per-question snapshots.
    dirty_questions: Dict[str, bool] = field(
        default_factory=lambda: {f"q{i}": True for i in range(1, 10)}
    )
    question_snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Optional trigger correlators.
    environment_fingerprint: Optional[str] = None
    agent_signature: Optional[str] = None

    def is_dirty(self, question_id: NineQuestionId) -> bool:
        return bool(self.dirty_questions.get(question_id, True))

    def mark_dirty(self, question_ids: List[NineQuestionId], *, reason: str) -> None:
        for qid in question_ids:
            self.dirty_questions[str(qid)] = True
        self.last_refresh_reason = str(reason)

    def mark_clean(self, question_id: NineQuestionId) -> None:
        self.dirty_questions[str(question_id)] = False

    def apply_question_result(
        self,
        *,
        question_id: NineQuestionId,
        tool_id: str,
        summary: str,
        confidence: float,
        context_updates: Dict[str, Any],
        trace_id: str,
        refreshed_at: Optional[datetime] = None,
        refresh_reason: str,
        driver_refs: List[str],
    ) -> None:
        timestamp = refreshed_at or _now()
        self.revision += 1
        self.snapshot_version += 1
        self.refreshed_at = timestamp
        self.last_refresh_reason = str(refresh_reason)
        self.question_driver_refs = list(driver_refs)

        snapshot = {
            "question_id": str(question_id),
            "tool_id": str(tool_id),
            "summary": str(summary),
            "confidence": float(confidence),
            "context_updates": dict(context_updates),
            "trace_id": str(trace_id),
            "updated_at": timestamp.isoformat(),
        }
        self.question_snapshots[str(question_id)] = snapshot
        if isinstance(context_updates, dict):
            self.current_context.update(context_updates)

        if str(question_id) == "q2":
            role_profile = context_updates.get("q2_role_profile")
            if isinstance(role_profile, dict) and role_profile.get("active_role"):
                self.current_role_hypothesis = str(role_profile["active_role"])

        self.mark_clean(question_id)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "snapshot_version": self.snapshot_version,
            "revision": self.revision,
            "last_refresh_reason": self.last_refresh_reason,
            "refreshed_at": self.refreshed_at.isoformat(),
            "question_driver_refs": list(self.question_driver_refs),
            "current_role_hypothesis": self.current_role_hypothesis,
            "current_context": dict(self.current_context),
            "active_constraints": list(self.active_constraints),
            "operator_patch": dict(self.operator_patch),
            "dirty_questions": dict(self.dirty_questions),
            "question_snapshots": dict(self.question_snapshots),
            "environment_fingerprint": self.environment_fingerprint,
            "agent_signature": self.agent_signature,
        }

