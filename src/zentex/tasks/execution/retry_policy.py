from __future__ import annotations

from typing import Any, Dict


def decide_retry(failure: Dict[str, Any] | None, retry_state: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
    if not failure:
        return {"decision": "no_failure", "retry_allowed": False, "retry_state": dict(retry_state or {})}
    policy = contract.get("retry_policy") if isinstance(contract.get("retry_policy"), dict) else {}
    max_attempts = int(policy.get("max_attempts") or retry_state.get("max_attempts") or 1)
    attempt_count = int(retry_state.get("attempt_count") or 0)
    retryable_failures = set(policy.get("retryable_failures") or [])
    failure_type = str(failure.get("failure_type") or "")
    retryable = bool(failure.get("retryable")) and failure_type in retryable_failures and attempt_count < max_attempts
    updated = dict(retry_state or {})
    updated.update(
        {
            "attempt_count": attempt_count + (1 if retryable else 0),
            "max_attempts": max_attempts,
            "last_failure_type": failure_type,
            "last_failure_code": failure.get("failure_code"),
        }
    )
    return {
        "decision": "retry" if retryable else "recover",
        "retry_allowed": retryable,
        "retry_state": updated,
    }
