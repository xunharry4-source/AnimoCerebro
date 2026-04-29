from __future__ import annotations

"""Runtime orchestration for Feature 53 LivingSelfModelEngine."""

from typing import Any, Optional

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


def update_living_self_model(
    kernel_service: Any,
    *,
    session_id: str,
    turn_result: dict[str, Any],
    recent_events: Optional[list[dict[str, Any]]] = None,
    working_memory_frame: Optional[dict[str, Any]] = None,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.self_model.update_from_turn_result(
        turn_result,
        recent_events=recent_events,
        working_memory_frame=working_memory_frame,
        trace_id=trace_id,
    )
    _append_entry(state, session_id=session_id, trace_id=trace_id, operation="update_from_turn_result", result=result)
    return _read_after_write(state, result)


def query_living_self_model(kernel_service: Any, *, session_id: str) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    return {
        "feature_code": "B2-53",
        "operation": "query_living_self_model",
        "query_visible": True,
        "living_self_model_status": "queried",
        "living_self_model": state.self_model.living_model_snapshot(),
    }


def detect_living_self_weakness_patterns(
    kernel_service: Any,
    *,
    session_id: str,
    recent_events: list[dict[str, Any]],
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.self_model.detect_weakness_pattern(recent_events)
    _append_entry(state, session_id=session_id, trace_id=trace_id, operation="detect_weakness_pattern", result=result)
    return _read_after_write(state, result)


def check_living_self_confidence_drift(
    kernel_service: Any,
    *,
    session_id: str,
    statements: list[dict[str, Any]],
    evidence: Optional[Any] = None,
    threshold: float = 0.25,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.self_model.check_confidence_drift(statements, evidence, threshold=threshold)
    _append_entry(state, session_id=session_id, trace_id=trace_id, operation="check_confidence_drift", result=result)
    return _read_after_write(state, result)


def apply_living_self_load_adjustment(
    kernel_service: Any,
    *,
    session_id: str,
    working_memory_frame: dict[str, Any],
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.self_model.apply_load_adjustment(working_memory_frame)
    _append_entry(state, session_id=session_id, trace_id=trace_id, operation="apply_load_adjustment", result=result)
    return _read_after_write(state, result)


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
    operation: str,
    result: dict[str, Any],
) -> None:
    model = result["living_self_model"]
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.living_self_model_updated,
            session_id=session_id,
            turn_id=str((model.get("update_sources") or [{}])[-1].get("source_ref") or ""),
            trace_id=trace_id or f"living-self:{operation}:{model['model_id']}",
            source="zentex.kernel.living_self_model_runtime",
            payload={
                "feature_code": "B2-53",
                "entry_type": "living_self_model_updated",
                "operation": operation,
                "model_id": model["model_id"],
                "current_state": model["current_state"],
                "recent_weakness_count": len(model["recent_weaknesses"]),
                "confidence_drift_count": len(model["confidence_drift_indicators"]),
                "living_self_model_status": result["living_self_model_status"],
            },
        )
    )


def _read_after_write(state: Any, result: dict[str, Any]) -> dict[str, Any]:
    queried = state.self_model.living_model_snapshot()
    return {
        **result,
        "read_after_write": True,
        "queried_living_self_model": queried,
    }
