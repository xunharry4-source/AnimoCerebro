from __future__ import annotations

from zentex.tasks.execution.graph_state import ExecutionGraphState
from zentex.tasks.execution.persistence import append_graph_node_io, mark_react_terminal
from zentex.tasks.execution.recovery import should_suspend, terminal_failure_result


async def recover_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    status = "suspended" if should_suspend(state.get("failure")) else "failed"
    result = terminal_failure_result(dict(state), status=status)
    task_dao = runtime.get("task_dao")
    if task_dao is not None:
        task_dao.update_task(
            str(state.get("task_id")),
            {
                "status": "suspended" if status == "suspended" else "failed",
                "last_error": str(result.get("error") or "")[:2000],
            },
        )
        mark_react_terminal(task_dao=task_dao, task_id=str(state.get("task_id")), run_id=str(state.get("run_id")), status=status, result=result)
    append_graph_node_io(
        task_dao=task_dao,
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="recover",
        node_type="recover",
        status=status,
        input_payload={"failure": state.get("failure")},
        output_payload=result,
        error=state.get("failure"),
    )
    updated: ExecutionGraphState = dict(state)
    updated["terminal_status"] = status
    updated["result"] = result
    updated["phase"] = status
    return updated
