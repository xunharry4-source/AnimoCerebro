from __future__ import annotations

from typing import Any, Dict


def check_before_act(state: Dict[str, Any]) -> Dict[str, Any]:
    if not state.get("arguments") and (state.get("arguments") not in ([], {})):
        return _failed("ARGUMENTS_MISSING", "Resolved arguments are missing before Act", retryable=False)
    preflight = state.get("preflight_result") if isinstance(state.get("preflight_result"), dict) else {}
    if preflight.get("passed") is not True:
        return _failed("PREFLIGHT_NOT_PASSED", "Act is blocked because preflight did not pass", retryable=False)
    return {"passed": True, "check_id": "execution_check_before", "failure_code": "", "message": ""}


def check_after_observe(state: Dict[str, Any]) -> Dict[str, Any]:
    attempt = state.get("current_attempt") if isinstance(state.get("current_attempt"), dict) else {}
    observations = state.get("observations") if isinstance(state.get("observations"), list) else []
    if not attempt:
        return _failed("ACTION_ATTEMPT_MISSING", "No action attempt was recorded", retryable=False)
    if not observations:
        return _failed("OBSERVATION_MISSING", "No observation was recorded after Act", retryable=True)
    if attempt.get("status") != "succeeded":
        return _failed(
            str(attempt.get("error_code") or "ACTION_ATTEMPT_FAILED"),
            str(attempt.get("error_message") or "Action attempt failed"),
            retryable=bool(attempt.get("retryable")),
        )
    return {"passed": True, "check_id": "execution_check_after", "failure_code": "", "message": ""}


def _failed(code: str, message: str, *, retryable: bool) -> Dict[str, Any]:
    return {
        "passed": False,
        "failure_type": "execution_check_failed",
        "failure_code": code,
        "message": message,
        "retryable": retryable,
    }
