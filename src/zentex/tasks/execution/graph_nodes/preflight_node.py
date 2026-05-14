from __future__ import annotations

from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io
from zentex.tasks.execution.preflight import run_preflight


async def preflight_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    result = await run_preflight(state.get("context") or {}, state.get("contract") or {}, runtime)
    updated: ExecutionGraphState = dict(state)
    updated["preflight_result"] = result
    if result.get("passed") is not True:
        updated = with_failure(
            updated,
            phase="preflight_failed",
            failure_type=str(result.get("failure_type") or "preflight_failed"),
            failure_code=str(result.get("failure_code") or "PREFLIGHT_FAILED"),
            message=str(result.get("message") or "Preflight failed"),
            retryable=bool(result.get("retryable")),
            details=result,
        )
        status = "failed"
    else:
        updated["phase"] = "execution_check_before_pending"
        status = "passed"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="preflight",
        node_type="preflight",
        status=status,
        input_payload={"executor_type": (state.get("context") or {}).get("executor_type")},
        output_payload=result,
        error=updated.get("failure") if status == "failed" else None,
    )
    return updated
