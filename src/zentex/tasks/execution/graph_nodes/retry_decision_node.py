from __future__ import annotations

from zentex.tasks.execution.graph_state import ExecutionGraphState
from zentex.tasks.execution.persistence import append_graph_node_io
from zentex.tasks.execution.retry_policy import decide_retry


async def retry_decision_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    decision = decide_retry(state.get("failure"), state.get("retry_state") or {}, state.get("contract") or {})
    updated: ExecutionGraphState = dict(state)
    updated["retry_state"] = decision.get("retry_state") or {}
    updated["phase"] = "preflight_pending" if decision.get("retry_allowed") else "recover_pending"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="retry_decision",
        node_type="retry",
        status="retry" if decision.get("retry_allowed") else "recover",
        input_payload={"failure": state.get("failure")},
        output_payload=decision,
    )
    return updated
