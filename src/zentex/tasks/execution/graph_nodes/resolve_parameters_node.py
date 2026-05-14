from __future__ import annotations

from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.parameter_resolver import resolve_parameters
from zentex.tasks.execution.persistence import append_graph_node_io


async def resolve_parameters_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    result = resolve_parameters(state.get("context") or {}, state.get("contract") or {})
    updated: ExecutionGraphState = dict(state)
    updated["parameter_resolution"] = result
    updated["arguments"] = result.get("arguments")
    if result["status"] == "parameter_gap":
        updated = with_failure(
            updated,
            phase="parameter_gap",
            failure_type="parameter_gap",
            failure_code="REQUIRED_PARAMETERS_MISSING",
            message=f"Required parameters missing: {', '.join(result.get('missing_parameters') or [])}",
            details=result,
        )
        status = "failed"
    elif result["status"] == "invalid_parameters":
        updated = with_failure(
            updated,
            phase="invalid_parameters",
            failure_type="contract_gap",
            failure_code="INVALID_PARAMETERS",
            message="Executor parameters do not satisfy parameter_schema",
            details=result,
        )
        status = "failed"
    else:
        updated["phase"] = "preflight_pending"
        status = "passed"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="resolve_parameters",
        node_type="resolver",
        status=status,
        input_payload={"required_parameters": (state.get("contract") or {}).get("required_parameters") or []},
        output_payload=result,
        error=updated.get("failure") if status == "failed" else None,
    )
    return updated
