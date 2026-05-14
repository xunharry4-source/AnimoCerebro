from __future__ import annotations

from zentex.tasks.execution.capability_verifier import verify_capability
from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io
from zentex.tasks.execution.validation_strategy import apply_validation_strategy


async def verify_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    rule_verdict = verify_capability(
        context=state.get("context") or {},
        observations=state.get("observations") or [],
        result_validation=state.get("result_validation") or {},
        contract=state.get("contract") or {},
    )
    strategy_verdict = await apply_validation_strategy(
        contract=state.get("contract") or {},
        rule_verdict=rule_verdict,
        context=state.get("context") or {},
        runtime=runtime,
    )
    verification = dict(rule_verdict)
    verification["validation_strategy_result"] = strategy_verdict
    verification["overall_passed"] = bool(strategy_verdict.get("passed"))
    verification["passed"] = bool(strategy_verdict.get("passed"))
    updated: ExecutionGraphState = dict(state)
    updated["verification_result"] = verification
    if verification.get("passed") is not True:
        updated = with_failure(
            updated,
            phase="verification_failed",
            failure_type="verification_failed",
            failure_code=str(strategy_verdict.get("failure_code") or verification.get("failure_code") or "VERIFICATION_FAILED"),
            message=str(strategy_verdict.get("message") or verification.get("summary") or "Verification failed"),
            retryable=False,
            details=verification,
        )
        status = "failed"
    else:
        updated["phase"] = "complete_pending"
        status = "passed"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="verify",
        node_type="verify",
        status=status,
        input_payload={"strategy": (state.get("contract") or {}).get("verification_strategy")},
        output_payload=verification,
        error=updated.get("failure") if status == "failed" else None,
    )
    return updated
