from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict


TerminalStatus = Literal["completed", "failed", "suspended"]


class ExecutionGraphState(TypedDict, total=False):
    task_id: str
    trace_id: str
    run_id: str
    phase: str
    context: Dict[str, Any]
    runtime: Dict[str, Any]
    contract: Dict[str, Any]
    profile: Dict[str, Any]
    plan: Dict[str, Any] | None
    arguments: Dict[str, Any] | List[Any] | None
    parameter_resolution: Dict[str, Any] | None
    preflight_result: Dict[str, Any] | None
    execution_check_result: Dict[str, Any] | None
    current_attempt: Dict[str, Any] | None
    observations: List[Dict[str, Any]]
    result_validation: Dict[str, Any] | None
    verification_result: Dict[str, Any] | None
    retry_state: Dict[str, Any]
    failure: Dict[str, Any] | None
    audit_events: List[Dict[str, Any]]
    terminal_status: TerminalStatus | None
    result: Dict[str, Any] | None


def with_failure(
    state: ExecutionGraphState,
    *,
    phase: str,
    failure_type: str,
    failure_code: str,
    message: str,
    retryable: bool = False,
    details: Dict[str, Any] | None = None,
) -> ExecutionGraphState:
    updated: ExecutionGraphState = dict(state)
    updated["phase"] = phase
    updated["failure"] = {
        "failure_type": failure_type,
        "failure_code": failure_code,
        "message": message,
        "retryable": retryable,
        "details": dict(details or {}),
    }
    return updated


def append_audit_event(
    state: ExecutionGraphState,
    event_type: str,
    payload: Dict[str, Any] | None = None,
) -> ExecutionGraphState:
    updated: ExecutionGraphState = dict(state)
    events = list(updated.get("audit_events") or [])
    events.append({"event_type": event_type, "payload": dict(payload or {})})
    updated["audit_events"] = events
    return updated
