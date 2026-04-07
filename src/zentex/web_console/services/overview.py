from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Optional

from plugins.weights.subjective_weight_plugin import WeightPluginAssembler
from zentex.core.models import BrainRuntimeState
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.session import BrainSession, BrainSessionSnapshot
from zentex.runtime.transcript import BrainTranscriptEntryType
from zentex.web_console.contracts.runtime import RuntimeOverviewPayload
from zentex.web_console.transcript_serialization import serialize_transcript_entry


def serialize_runtime_state(runtime_state: BrainRuntimeState) -> Dict[str, Any]:
    return {
        "runtime_id": runtime_state.runtime_id,
        "started_at": runtime_state.started_at.astimezone(timezone.utc).isoformat(),
        "active_session_ids": runtime_state.active_session_ids,
        "default_workspace": runtime_state.default_workspace,
        "identity_kernel_ref": runtime_state.identity_kernel_ref,
        "tool_registry_version": runtime_state.tool_registry_version,
        "transcript_store_status": runtime_state.transcript_store_status,
        "memory_store_status": runtime_state.memory_store_status,
        "read_only_mode": runtime_state.read_only_mode,
        "degraded_mode": runtime_state.degraded_mode,
        "manual_confirmation_required": runtime_state.manual_confirmation_required,
        "last_runtime_snapshot_at": runtime_state.last_runtime_snapshot_at.astimezone(timezone.utc).isoformat(),
    }


def serialize_session_snapshot(snapshot: Optional[BrainSessionSnapshot]) -> Dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "session_id": snapshot.session_id,
        "turn_count": snapshot.turn_count,
        "active_goal_titles": snapshot.active_goal_titles,
        "current_focus_summary": snapshot.current_focus_summary,
        "overdue_items": snapshot.overdue_items,
        "current_reasoning_mode": snapshot.current_reasoning_mode,
        "degraded_flags": snapshot.degraded_flags,
        "last_turn_at": snapshot.last_turn_at.astimezone(timezone.utc).isoformat()
        if snapshot.last_turn_at is not None
        else None,
    }


def build_overview_payload(
    runtime: BrainRuntime,
    session: Optional[BrainSession],
    weight_assembler: Optional[WeightPluginAssembler] = None,
) -> RuntimeOverviewPayload:
    runtime_state = runtime.get_runtime_state()
    session_snapshot = session.get_snapshot() if session is not None else None
    working_memory = (
        session.last_working_memory if session is not None and isinstance(session.last_working_memory, dict) else {}
    )
    metacognition = (
        session.last_metacognition if session is not None and isinstance(session.last_metacognition, dict) else {}
    )
    living_self_model = (
        session.last_living_self_model
        if session is not None and isinstance(session.last_living_self_model, dict)
        else {}
    )
    temporal_agenda = (
        session.last_temporal_agenda if session is not None and isinstance(session.last_temporal_agenda, dict) else {}
    )

    weight_snapshot = weight_assembler.snapshot() if weight_assembler is not None else None
    all_entries = runtime.transcript_store.get_entries_snapshot()
    recent_entries = all_entries[-20:]
    recent_events = [serialize_transcript_entry(entry) for entry in reversed(recent_entries)]
    last_intervention_entry = next(
        (
            entry
            for entry in reversed(all_entries)
            if entry.entry_type == BrainTranscriptEntryType.HUMAN_INTERVENTION_APPLIED
        ),
        None,
    )

    runtime_payload = serialize_runtime_state(runtime_state)
    runtime_payload["intervention_state"] = getattr(runtime, "intervention_state", None)

    return RuntimeOverviewPayload(
        runtime=runtime_payload,
        session=serialize_session_snapshot(session_snapshot),
        working_memory=working_memory,
        metacognition=metacognition,
        living_self_model=living_self_model,
        temporal_agenda=temporal_agenda,
        recent_events=recent_events,
        last_intervention_event=serialize_transcript_entry(last_intervention_entry)
        if last_intervention_entry is not None
        else None,
        active_weight_plugin_id=weight_snapshot.active_weight_plugin_id if weight_snapshot is not None else None,
        weight_fallback_occurred=weight_snapshot.weight_fallback_occurred if weight_snapshot is not None else False,
        weight_profile=weight_snapshot.model_dump(mode="json") if weight_snapshot is not None else {},
    )

