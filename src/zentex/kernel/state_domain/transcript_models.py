from __future__ import annotations
"""Transcript model types — plain dataclasses for high-throughput logging."""


import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

UTC = timezone.utc


class TranscriptEntryType(str, Enum):
    turn_start = "turn_start"
    phase_result = "phase_result"
    nine_q_update = "nine_q_update"
    bootstrap_start = "bootstrap_start"
    bootstrap_end = "bootstrap_end"
    turn_end = "turn_end"
    error = "error"
    state_change = "state_change"
    # Cross-module audit flow boundary marker.
    # Payload always contains audit_id, flow_type, source_module, event ("flow_start"|"flow_end").
    flow_audit = "flow_audit"
    
    # Cognitive integration types (mirrored from BrainTranscriptEntryType for compatibility)
    model_provider_invoked = "model_provider_invoked"
    model_provider_completed = "model_provider_completed"
    model_provider_failed = "model_provider_failed"
    plugin_audit_event = "plugin_audit_event"
    context_snapshot_written = "context_snapshot_written"
    session_started = "session_started"
    working_memory_updated = "working_memory_updated"
    temporal_agenda_updated = "temporal_agenda_updated"
    living_self_model_updated = "living_self_model_updated"
    conflict_snapshot_written = "conflict_snapshot_written"
    counterfactual_completed = "counterfactual_completed"
    interaction_mind_updated = "interaction_mind_updated"
    metacognition_decided = "metacognition_decided"
    cognitive_tool_invoked = "cognitive_tool_invoked"
    cognitive_tool_completed = "cognitive_tool_completed"
    decision_synthesized = "decision_synthesized"
    reflection_persisted = "reflection_persisted"
    consolidation_completed = "consolidation_completed"
    consolidation_failed = "consolidation_failed"
    human_intervention_applied = "human_intervention_applied"
    nine_question_state_updated = "nine_question_state_updated"
    learning_engine_event = "learning_engine_event"


@dataclass
class TranscriptEntry:
    """A single record in the transcript log.

    Uses a plain dataclass (not Pydantic) for minimal serialisation overhead
    during high-frequency turn processing.
    """

    entry_type: TranscriptEntryType
    session_id: str
    turn_id: str = ""
    trace_id: str = ""
    source: str = "kernel"
    payload: dict = field(default_factory=dict)
    # Set in __post_init__
    entry_id: str = field(default="")
    timestamp: str = field(default="")

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()
        if not self.trace_id and self.payload:
            # Try to resolve trace_id from payload if missing from top-level
            self.trace_id = str(self.payload.get("trace_id") or "")


@dataclass
class TurnAuditSummary:
    """Aggregated statistics derived from a completed turn's transcript entries."""

    turn_id: str
    session_id: str
    phase_count: int
    error_count: int
    started_at: str
    ended_at: str
    duration_ms: float
