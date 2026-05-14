from __future__ import annotations

from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io


async def reason_node(state: ExecutionGraphState) -> ExecutionGraphState:
    contract = state.get("contract") or {}
    context = state.get("context") or {}
    runtime = state.get("runtime") or {}
    plan = {
        "task_id": state.get("task_id"),
        "trace_id": state.get("trace_id"),
        "next_action": "resolve_parameters",
        "action_reason": "Capability contract loaded; resolve executor parameters before preflight.",
        "required_capability_contract": contract,
        "expected_observations": contract.get("observation_sources") or [],
        "stop_conditions": ["verification_passed", "parameter_gap", "non_retryable_failure"],
    }
    strategy = str(contract.get("verification_strategy") or "rule")
    if strategy in {"llm", "hybrid"} and runtime.get("llm_reason_gateway") is None:
        return with_failure(
            state,
            phase="reason_failed",
            failure_type="llm_unavailable",
            failure_code="LLM_REASON_REQUIRED_BUT_NOT_AVAILABLE",
            message="Contract requires LLM-capable reasoning but no llm_reason_gateway was provided",
        )
    updated: ExecutionGraphState = dict(state)
    updated.update({"phase": "parameters_pending", "plan": plan})
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="reason",
        node_type="reason",
        status="passed",
        input_payload={"executor_type": context.get("executor_type"), "capability": context.get("capability")},
        output_payload={"next_action": plan["next_action"], "verification_strategy": strategy},
    )
    return updated
