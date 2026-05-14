from __future__ import annotations

from zentex.tasks.execution.execution_check import check_after_observe, check_before_act
from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io


async def execution_check_before_node(state: ExecutionGraphState) -> ExecutionGraphState:
    return _record_check(state, "execution_check_before", check_before_act(dict(state)), next_phase="act_pending")


async def execution_check_after_node(state: ExecutionGraphState) -> ExecutionGraphState:
    return _record_check(state, "execution_check_after", check_after_observe(dict(state)), next_phase="result_validation_pending")


def _record_check(state: ExecutionGraphState, node_id: str, result: dict, *, next_phase: str) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    updated: ExecutionGraphState = dict(state)
    updated["execution_check_result"] = result
    if result.get("passed") is not True:
        updated = with_failure(
            updated,
            phase=f"{node_id}_failed",
            failure_type=str(result.get("failure_type") or "execution_check_failed"),
            failure_code=str(result.get("failure_code") or "EXECUTION_CHECK_FAILED"),
            message=str(result.get("message") or "Execution check failed"),
            retryable=bool(result.get("retryable")),
            details=result,
        )
        status = "failed"
    else:
        updated["phase"] = next_phase
        status = "passed"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id=node_id,
        node_type="execution_check",
        status=status,
        input_payload={"phase": node_id},
        output_payload=result,
        error=updated.get("failure") if status == "failed" else None,
    )
    return updated
