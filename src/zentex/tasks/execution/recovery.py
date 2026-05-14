from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def terminal_failure_result(state: Dict[str, Any], *, status: str = "failed") -> Dict[str, Any]:
    failure = state.get("failure") if isinstance(state.get("failure"), dict) else {}
    return {
        "succeeded": False,
        "status": status,
        "task_center_synchronized": False,
        "error": failure.get("message") or "ReAct execution failed",
        "error_code": failure.get("failure_code") or "REACT_EXECUTION_FAILED",
        "failure": failure,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


def should_suspend(failure: Dict[str, Any] | None) -> bool:
    if not failure:
        return False
    return str(failure.get("failure_type") or "") in {"parameter_gap", "contract_gap", "permission_gap"}
