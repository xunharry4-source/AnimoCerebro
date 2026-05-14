from __future__ import annotations

from typing import Any, Dict


def route_after_context(state: Dict[str, Any]) -> str:
    return "recover" if state.get("failure") else "reason"


def route_after_reason(state: Dict[str, Any]) -> str:
    return "recover" if state.get("failure") else "resolve_parameters"


def route_after_resolve_parameters(state: Dict[str, Any]) -> str:
    return "recover" if state.get("failure") else "preflight"


def route_after_preflight(state: Dict[str, Any]) -> str:
    return "retry_decision" if state.get("failure") else "execution_check_before"


def route_after_execution_check_before(state: Dict[str, Any]) -> str:
    return "recover" if state.get("failure") else "act"


def route_after_act(state: Dict[str, Any]) -> str:
    return "retry_decision" if state.get("failure") else "observe"


def route_after_observe(state: Dict[str, Any]) -> str:
    return "retry_decision" if state.get("failure") else "execution_check_after"


def route_after_execution_check_after(state: Dict[str, Any]) -> str:
    return "retry_decision" if state.get("failure") else "result_validate"


def route_after_result_validate(state: Dict[str, Any]) -> str:
    return "retry_decision" if state.get("failure") else "verify"


def route_after_verify(state: Dict[str, Any]) -> str:
    return "retry_decision" if state.get("failure") else "complete"


def route_after_retry_decision(state: Dict[str, Any]) -> str:
    return "preflight" if state.get("phase") == "preflight_pending" else "recover"
