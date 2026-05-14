from __future__ import annotations

from zentex.tasks.execution.dispatch import dispatch_action
from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io


async def act_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    attempt = await dispatch_action(state.get("context") or {}, runtime)
    updated: ExecutionGraphState = dict(state)
    updated["current_attempt"] = attempt
    if attempt.get("status") != "succeeded":
        updated = with_failure(
            updated,
            phase="act_failed",
            failure_type="execution_failure",
            failure_code=str(attempt.get("error_code") or "ACT_FAILED"),
            message=str(attempt.get("error_message") or "Act failed"),
            retryable=bool(attempt.get("retryable")),
            details=attempt,
        )
        status = "failed"
    else:
        updated["phase"] = "observe_pending"
        status = "passed"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="act",
        node_type="act",
        status=status,
        input_payload={"executor_type": (state.get("context") or {}).get("executor_type"), "arguments": state.get("arguments")},
        output_payload={"attempt_id": attempt.get("attempt_id"), "status": attempt.get("status"), "error_code": attempt.get("error_code")},
        error=updated.get("failure") if status == "failed" else None,
    )
    return updated
