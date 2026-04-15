from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict

JSONValue = (
    None
    | bool
    | int
    | float
    | str
    | list["JSONValue"]
    | dict[str, "JSONValue"]
)


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
        return {
            "entry_id": self.entry_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "entry_type": self.entry_type.value,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "source": self.source,
            "trace_id": self.trace_id,
        }
