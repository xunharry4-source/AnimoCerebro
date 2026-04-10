from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, List["JSONValue"], Dict[str, "JSONValue"]]


from datetime import timezone


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


from typing import Literal


class BrainTranscriptEntryType(str, Enum):
    SESSION_STARTED = "session_started"
    TURN_STARTED = "turn_started"
    CONTEXT_SNAPSHOT_WRITTEN = "context_snapshot_written"
    WORKING_MEMORY_UPDATED = "working_memory_updated"
    TEMPORAL_AGENDA_UPDATED = "temporal_agenda_updated"
    LIVING_SELF_MODEL_UPDATED = "living_self_model_updated"
    CONFLICT_SNAPSHOT_WRITTEN = "conflict_snapshot_written"
    COUNTERFACTUAL_COMPLETED = "counterfactual_completed"
    INTERACTION_MIND_UPDATED = "interaction_mind_updated"
    METACOGNITION_DECIDED = "metacognition_decided"
    COGNITIVE_TOOL_INVOKED = "cognitive_tool_invoked"
    COGNITIVE_TOOL_COMPLETED = "cognitive_tool_completed"
    MODEL_PROVIDER_INVOKED = "model_provider_invoked"
    MODEL_PROVIDER_COMPLETED = "model_provider_completed"
    MODEL_PROVIDER_FAILED = "model_provider_failed"
    DECISION_SYNTHESIZED = "decision_synthesized"
    REFLECTION_PERSISTED = "reflection_persisted"
    CONSOLIDATION_COMPLETED = "consolidation_completed"
    CONSOLIDATION_FAILED = "consolidation_failed"
    HUMAN_INTERVENTION_APPLIED = "human_intervention_applied"
    NINE_QUESTION_STATE_UPDATED = "nine_question_state_updated"
    PLUGIN_AUDIT_EVENT = "plugin_audit_event"
    LEARNING_ENGINE_EVENT = "learning_engine_event"
    TURN_FINISHED = "turn_finished"


@dataclass(frozen=True)
class BrainTranscriptEntry:
    entry_id: str
    session_id: str
    turn_id: str
    entry_type: BrainTranscriptEntryType
    timestamp: datetime
    payload: JSONValue
    source: str
    trace_id: str

    def to_record(self) -> Dict[str, Any]:
        from datetime import timezone
        return {
            "entry_id": self.entry_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "entry_type": self.entry_type.value,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "payload": self.payload,
            "source": self.source,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "BrainTranscriptEntry":
        return cls(
            entry_id=str(record["entry_id"]),
            session_id=str(record["session_id"]),
            turn_id=str(record["turn_id"]),
            entry_type=BrainTranscriptEntryType(record["entry_type"]),
            timestamp=datetime.fromisoformat(str(record["timestamp"])),
            payload=record["payload"],
            source=str(record["source"]),
            trace_id=str(record["trace_id"]),
        )


@dataclass(frozen=True)
class BrainTurnResult:
    """
    ThinkLoop 单轮执行完成后的完整交接对象。

    Responsibilities:
    - 承载单轮九阶段认知产物，供 `BrainSession.advance_turn` 统一落盘。
    - 保存 turn 级总 trace 与 phase 级 trace 映射，确保后续 Transcript 回放时能
      还原“哪一个阶段触发了哪一次大模型调用”。

    Field semantics:
    - `trace_id`: 当前 turn 的总追踪标识，用于串联 `session_started`、
      `turn_started`、`turn_finished` 等 turn 级事件。
    - `phase_trace_ids`: phase 到 trace 的映射，用于把 `context_snapshot`、
      `decision` 等关键阶段与对应的大模型调用严格绑定。
    """

    session_id: str
    turn_id: str
    started_at: datetime
    finished_at: datetime
    context_snapshot: Dict[str, Any]
    working_memory: Dict[str, Any]
    temporal_agenda: Dict[str, Any]
    living_self_model: Dict[str, Any]
    metacognition: Dict[str, Any]
    conflict_snapshot: Dict[str, Any]
    counterfactual_simulation: Dict[str, Any]
    interaction_mind: Dict[str, Any]
    tool_invocations: List[Dict[str, Any]] = field(default_factory=list)
    cognitive_tool_context: Dict[str, Any] = field(default_factory=dict)
    decision_summary: Dict[str, Any] = field(default_factory=dict)
    reflection_record: Dict[str, Any] = field(default_factory=dict)
    consolidation: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    phase_trace_ids: Dict[str, str] = field(default_factory=dict)
    nine_question_state: Optional[Any] = None
    evolution_result: Optional[Dict[str, Any]] = None
