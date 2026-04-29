from __future__ import annotations

"""Runtime orchestration for Feature 52 WorkingMemoryController."""

from typing import Any, Optional

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


def update_working_memory_frame(
    kernel_service: Any,
    *,
    session_id: str,
    tick_id: str,
    new_candidates: list[dict[str, Any]],
    attention_budget: Optional[dict[str, Any]] = None,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.working_memory.update_frame(
        tick_id=tick_id,
        new_candidates=new_candidates,
        attention_budget=attention_budget,
    )
    _append_update_entry(
        state,
        session_id=session_id,
        tick_id=tick_id,
        trace_id=trace_id,
        operation="update_frame",
        result=result,
    )
    _append_shift_entries(
        state,
        session_id=session_id,
        tick_id=tick_id,
        trace_id=trace_id,
        events=result["attention_shift_events"],
    )
    return _read_after_write(state, result)


def interrupt_working_memory_focus(
    kernel_service: Any,
    *,
    session_id: str,
    tick_id: str,
    high_risk_item: dict[str, Any],
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.working_memory.interrupt(high_risk_item=high_risk_item, tick_id=tick_id)
    _append_update_entry(
        state,
        session_id=session_id,
        tick_id=tick_id,
        trace_id=trace_id,
        operation="interrupt",
        result=result,
    )
    _append_shift_entries(
        state,
        session_id=session_id,
        tick_id=tick_id,
        trace_id=trace_id,
        events=result["attention_shift_events"],
    )
    return _read_after_write(state, result)


def resume_working_memory_focus(
    kernel_service: Any,
    *,
    session_id: str,
    tick_id: str,
    focus_id: str,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.working_memory.resume(focus_id=focus_id, tick_id=tick_id)
    _append_update_entry(
        state,
        session_id=session_id,
        tick_id=tick_id,
        trace_id=trace_id,
        operation="resume",
        result=result,
    )
    _append_shift_entries(
        state,
        session_id=session_id,
        tick_id=tick_id,
        trace_id=trace_id,
        events=result["attention_shift_events"],
    )
    return _read_after_write(state, result)


def mark_working_memory_considered(
    kernel_service: Any,
    *,
    session_id: str,
    ref_id: str,
    tick_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.working_memory.mark_considered(ref_id=ref_id, tick_id=tick_id)
    _append_update_entry(
        state,
        session_id=session_id,
        tick_id=tick_id or result["frame"]["tick_id"],
        trace_id=trace_id,
        operation="mark_considered",
        result=result,
    )
    return _read_after_write(state, result)


def query_working_memory_frame(
    kernel_service: Any,
    *,
    session_id: str,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    frame = state.working_memory.frame_snapshot()
    return {
        "feature_code": "B1-52",
        "operation": "query_frame",
        "query_visible": True,
        "working_memory_status": "queried",
        "frame": frame,
    }


def _require_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    return state


def _append_update_entry(
    state: Any,
    *,
    session_id: str,
    tick_id: str,
    trace_id: Optional[str],
    operation: str,
    result: dict[str, Any],
) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.working_memory_updated,
            session_id=session_id,
            turn_id=tick_id,
            trace_id=trace_id or f"working-memory:{operation}:{result['frame']['frame_id']}",
            source="zentex.kernel.working_memory_runtime",
            payload={
                "feature_code": "B1-52",
                "entry_type": "working_memory_updated",
                "operation": operation,
                "frame_id": result["frame"]["frame_id"],
                "tick_id": tick_id,
                "active_focus_ids": result["frame"]["active_focus_ids"],
                "suspended_focus_ids": result["frame"]["suspended_focus_ids"],
                "recently_considered_refs": result["frame"]["recently_considered_refs"],
                "accepted_focus_ids": result["accepted_focus_ids"],
                "rejected_candidates": result["rejected_candidates"],
            },
        )
    )


def _append_shift_entries(
    state: Any,
    *,
    session_id: str,
    tick_id: str,
    trace_id: Optional[str],
    events: list[dict[str, Any]],
) -> None:
    for event in events:
        state.transcript.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.working_memory_updated,
                session_id=session_id,
                turn_id=tick_id,
                trace_id=trace_id or f"attention-shift:{event['event_id']}",
                source="zentex.kernel.working_memory_runtime",
                payload={
                    "feature_code": "B1-52",
                    "entry_type": "attention_shift_event",
                    **event,
                },
            )
        )


def _read_after_write(state: Any, result: dict[str, Any]) -> dict[str, Any]:
    queried_frame = state.working_memory.frame_snapshot()
    return {
        **result,
        "read_after_write": True,
        "queried_frame": queried_frame,
    }
