from __future__ import annotations

from uuid import uuid4

from zentex.tasks.execution.capability_contract import resolve_capability_contract
from zentex.tasks.execution.execution_context import (
    build_execution_context,
    dispatch_from_task,
    metadata_from_task,
    normalize_task_payload,
)
from zentex.tasks.execution.executor_profiles import resolve_executor_profile, validate_dispatch_against_profile
from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io


async def load_context_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    task_dao = runtime.get("task_dao")
    task_id = str(state.get("task_id") or "")
    run_id = str(state.get("run_id") or f"react-run-{uuid4().hex}")
    if task_dao is None:
        return with_failure(state, phase="context_invalid", failure_type="contract_gap", failure_code="TASK_DAO_MISSING", message="TaskDAO is required")
    raw_task = task_dao.get_task(task_id)
    if raw_task is None:
        return with_failure(state, phase="context_invalid", failure_type="contract_gap", failure_code="TASK_NOT_FOUND", message=f"Task {task_id} not found")
    task = normalize_task_payload(raw_task)
    metadata = metadata_from_task(task)
    dispatch = dispatch_from_task(task)
    executor_type = str(dispatch.get("executor_type") or "")
    if not executor_type:
        return with_failure(state, phase="context_invalid", failure_type="contract_gap", failure_code="EXECUTOR_TYPE_MISSING", message="Task has no concrete executor type")
    profile = resolve_executor_profile(executor_type)
    missing = validate_dispatch_against_profile(dispatch, profile)
    if missing:
        return with_failure(
            state,
            phase="context_invalid",
            failure_type="contract_gap",
            failure_code="EXECUTOR_DISPATCH_FIELDS_MISSING",
            message=f"Task dispatch is missing required fields: {', '.join(missing)}",
            details={"missing_fields": missing},
        )
    context = build_execution_context(task, dispatch).to_dict()
    context["dispatch"] = dispatch
    context["profile"] = profile.to_dict()
    contract = resolve_capability_contract(
        task=task,
        metadata=metadata,
        dispatch=dispatch,
        profile=profile,
        owner_ref=context["owner_ref"],
    ).to_dict()
    updated: ExecutionGraphState = dict(state)
    updated.update(
        {
            "run_id": run_id,
            "trace_id": context["trace_id"],
            "phase": "context_loaded",
            "context": context,
            "profile": profile.to_dict(),
            "contract": contract,
            "retry_state": {"attempt_count": 0, "max_attempts": contract.get("retry_policy", {}).get("max_attempts", 1)},
            "observations": [],
            "audit_events": [],
            "failure": None,
        }
    )
    append_graph_node_io(
        task_dao=task_dao,
        task_id=task_id,
        run_id=run_id,
        node_id="load_context",
        node_type="context",
        status="passed",
        input_payload={"task_id": task_id},
        output_payload={"executor_type": executor_type, "capability": context.get("capability"), "profile": profile.execution_profile_id},
    )
    return updated
