from __future__ import annotations

"""Runtime orchestration for Feature 56 CognitiveConflictEngine."""

from typing import Any, Optional

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


def detect_cognitive_conflicts(
    kernel_service: Any,
    *,
    session_id: str,
    working_memory: dict[str, Any],
    goals: Optional[list[dict[str, Any]]] = None,
    nine_q_state: Optional[dict[str, Any]] = None,
    memory_recalls: Optional[list[dict[str, Any]]] = None,
    budget: Optional[dict[str, Any]] = None,
    self_model: Optional[dict[str, Any]] = None,
    agenda: Optional[list[dict[str, Any]]] = None,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    reports = state.conflict_engine.detect(
        working_memory=working_memory,
        goals=goals or [],
        nine_q_state=nine_q_state or {},
        memory_recalls=memory_recalls or [],
        budget=budget or {},
        self_model=self_model or state.self_model.snapshot(),
        agenda=agenda or [],
    )
    triggers = state.conflict_engine.generate_triggers(reports)
    result = {
        "feature_code": "B5-56",
        "operation": "detect_cognitive_conflicts",
        "cognitive_conflict_status": "detected",
        "deterministic": True,
        "llm_required": False,
        "conflict_reports": [_dump(report) for report in reports],
        "self_correction_triggers": [_dump(trigger) for trigger in triggers],
        "reconciliation_plans": [_dump(report.reconciliation_plan) for report in reports if report.reconciliation_plan is not None],
        "snapshot_version": state.conflict_engine.snapshot_version,
        "brain_scope": state.conflict_engine.brain_scope,
    }
    _append_entry(state, session_id=session_id, trace_id=trace_id, result=result)
    return _read_after_write(state, result)


def query_cognitive_conflicts(kernel_service: Any, *, session_id: str) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    snapshot = state.conflict_engine.snapshot()
    unresolved = [_dump(report) for report in snapshot.unresolved_conflicts]
    triggers = [_dump(trigger) for trigger in state.conflict_engine.generate_triggers()]
    return {
        "feature_code": "B5-56",
        "operation": "query_cognitive_conflicts",
        "query_visible": True,
        "cognitive_conflict_status": "queried",
        "conflict_reports": unresolved,
        "self_correction_triggers": triggers,
        "snapshot_version": snapshot.snapshot_version,
        "brain_scope": snapshot.brain_scope,
    }


def detect_cognitive_conflicts_phase4(
    kernel_service: Any,
    *,
    session_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    working_memory = context.get("working_memory") or context.get("working_memory_frame") or state.working_memory.frame_snapshot()
    return detect_cognitive_conflicts(
        kernel_service,
        session_id=session_id,
        working_memory=working_memory,
        goals=context.get("goals") or context.get("current_goals") or [],
        nine_q_state=context.get("nine_q_state") or context.get("nine_question_state") or {},
        memory_recalls=context.get("memory_recalls") or [],
        budget=context.get("budget") or context.get("reasoning_budget") or {},
        self_model=context.get("self_model") or context.get("living_self_model") or state.self_model.snapshot(),
        agenda=context.get("agenda") or context.get("cognitive_agenda") or [],
        trace_id=context.get("trace_id"),
    )


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
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.conflict_snapshot_written,
            session_id=session_id,
            turn_id="",
            trace_id=trace_id or f"cognitive-conflict:{session_id}:{len(result['conflict_reports'])}",
            source="zentex.kernel.cognitive_conflict_runtime",
            payload={
                "feature_code": "B5-56",
                "entry_type": "conflict_snapshot_written",
                "operation": result["operation"],
                "conflict_report_count": len(result["conflict_reports"]),
                "trigger_count": len(result["self_correction_triggers"]),
                "conflict_types": [item["conflict_type"] for item in result["conflict_reports"]],
                "snapshot_version": result["snapshot_version"],
                "brain_scope": result["brain_scope"],
                "cognitive_conflict_status": result["cognitive_conflict_status"],
            },
        )
    )


def _read_after_write(state: Any, result: dict[str, Any]) -> dict[str, Any]:
    snapshot = state.conflict_engine.snapshot()
    return {
        **result,
        "read_after_write": True,
        "queried_conflict_reports": [_dump(report) for report in snapshot.unresolved_conflicts],
    }


def _dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return dict(getattr(value, "__dict__", {}))
