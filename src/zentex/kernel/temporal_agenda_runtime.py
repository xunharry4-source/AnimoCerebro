from __future__ import annotations

"""Runtime orchestration for Feature 55 CognitiveTemporalEngine."""

from typing import Any, Optional

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


def tick_temporal_agenda(
    kernel_service: Any,
    *,
    session_id: str,
    current_time: str,
    agenda_items: list[dict[str, Any]],
    brain_scope: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    temporal_state = state.temporal.tick_agenda(
        current_time=current_time,
        agenda_items=agenda_items,
        brain_scope=brain_scope,
    )
    result = {
        "feature_code": "B3-55",
        "operation": "tick_agenda",
        "temporal_agenda_status": "updated",
        "deterministic": True,
        "llm_required": False,
        "temporal_agenda_state": temporal_state,
    }
    _append_entry(state, session_id=session_id, trace_id=trace_id, result=result)
    return _read_after_write(state, result)


def query_temporal_agenda_state(kernel_service: Any, *, session_id: str) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    return {
        "feature_code": "B3-55",
        "operation": "query_temporal_agenda_state",
        "query_visible": True,
        "temporal_agenda_status": "queried",
        "temporal_agenda_state": state.temporal.temporal_agenda_snapshot(),
    }


def _require_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    return state


def _append_entry(
    state: Any,
    *,
    session_id: str,
    trace_id: Optional[str],
    result: dict[str, Any],
) -> None:
    temporal_state = result["temporal_agenda_state"]
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.temporal_agenda_updated,
            session_id=session_id,
            turn_id=temporal_state["state_id"],
            trace_id=trace_id or f"temporal-agenda:{temporal_state['state_id']}",
            source="zentex.kernel.temporal_agenda_runtime",
            payload={
                "feature_code": "B3-55",
                "entry_type": "temporal_agenda_updated",
                "operation": "tick_agenda",
                "state_id": temporal_state["state_id"],
                "snapshot_version": temporal_state["snapshot_version"],
                "brain_scope": temporal_state["brain_scope"],
                "review_now_item_ids": temporal_state["review_now_item_ids"],
                "expired_item_ids": temporal_state["expired_item_ids"],
                "suppressed_item_ids": temporal_state["suppressed_item_ids"],
                "temporal_agenda_status": result["temporal_agenda_status"],
            },
        )
    )


def _read_after_write(state: Any, result: dict[str, Any]) -> dict[str, Any]:
    queried = state.temporal.temporal_agenda_snapshot()
    return {
        **result,
        "read_after_write": True,
        "queried_temporal_agenda_state": queried,
    }
