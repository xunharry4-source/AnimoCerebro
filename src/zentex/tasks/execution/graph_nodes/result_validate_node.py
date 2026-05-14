from __future__ import annotations

from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io
from zentex.tasks.execution.result_validator import validate_result


async def result_validate_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    result = validate_result(
        state.get("current_attempt") if isinstance(state.get("current_attempt"), dict) else {},
        state.get("observations") or [],
        state.get("contract") or {},
    )
    updated: ExecutionGraphState = dict(state)
    updated["result_validation"] = result
    if result.get("passed") is not True:
        updated = with_failure(
            updated,
            phase="result_validation_failed",
            failure_type="result_validation_failed",
            failure_code=str(result.get("failure_code") or "RESULT_VALIDATION_FAILED"),
            message="Executor result failed capability output contract validation",
            retryable=bool(result.get("retryable")),
            details=result,
        )
        status = "failed"
    else:
        updated["phase"] = "verify_pending"
        status = "passed"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="result_validate",
        node_type="result_validate",
        status=status,
        input_payload={"attempt_id": (state.get("current_attempt") or {}).get("attempt_id") if isinstance(state.get("current_attempt"), dict) else ""},
        output_payload=result,
        error=updated.get("failure") if status == "failed" else None,
    )
    return updated
