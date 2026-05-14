from __future__ import annotations

import json

from zentex.tasks.execution.completion_envelope import build_completion_envelope
from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.persistence import append_graph_node_io, mark_react_terminal, utc_now


async def complete_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    task_dao = runtime.get("task_dao")
    task_service = runtime.get("task_service")
    task_id = str(state.get("task_id"))
    attempt = state.get("current_attempt") if isinstance(state.get("current_attempt"), dict) else {}
    attempt_result = attempt.get("result") if isinstance(attempt.get("result"), dict) else {}
    completion_envelope = build_completion_envelope(
        task_id=task_id,
        run_id=str(state.get("run_id")),
        attempt=attempt,
        context=state.get("context") or {},
        observations=state.get("observations") or [],
    )
    if (state.get("verification_result") or {}).get("passed") is not True:
        return with_failure(state, phase="complete_failed", failure_type="verification_failed", failure_code="VERIFICATION_MISSING", message="Cannot complete without a passing verification result")

    result = {
        "succeeded": True,
        "status": "completed",
        "task_center_synchronized": bool(attempt_result.get("task_center_synchronized")),
        "actual_outcome": completion_envelope["actual_outcome"],
        "raw_executor_result": attempt_result,
        "external_execution": completion_envelope["external_execution"],
        "evidence": completion_envelope["evidence"],
        "verification_result": state.get("verification_result"),
        "finished_at": utc_now(),
    }
    if not result["task_center_synchronized"] and task_service is not None and callable(getattr(task_service, "complete_task_with_verification", None)):
        completion = await task_service.complete_task_with_verification(
            task_id,
            result=completion_envelope,
            remarks="LangGraph ReAct execution completed",
        )
        result["completion"] = completion
        result["task_center_synchronized"] = isinstance(completion, dict) and completion.get("success") is True
        if result["task_center_synchronized"]:
            await _ensure_task_outcome_readback(
                task_service=task_service,
                task_id=task_id,
                completion_envelope=completion_envelope,
                verification_result=state.get("verification_result") or {},
            )
    elif task_dao is not None:
        task_dao.update_task(
            task_id,
            {
                "status": "done",
                "progress": 1.0,
                "completed_at": utc_now(),
                "execution_finished_at": utc_now(),
                "execution_output": json.dumps(attempt_result, ensure_ascii=False, default=str),
                "last_error": None,
            },
        )
        result["task_center_synchronized"] = True
    if not result["task_center_synchronized"]:
        return with_failure(state, phase="complete_failed", failure_type="writeback_failed", failure_code="TASK_COMPLETION_WRITEBACK_FAILED", message="Task completion writeback failed", retryable=False, details=result)

    mark_react_terminal(task_dao=task_dao, task_id=task_id, run_id=str(state.get("run_id")), status="completed", result=result)
    append_graph_node_io(
        task_dao=task_dao,
        task_id=task_id,
        run_id=str(state.get("run_id")),
        node_id="complete",
        node_type="complete",
        status="passed",
        input_payload={"verification_result": state.get("verification_result")},
        output_payload=result,
    )
    updated: ExecutionGraphState = dict(state)
    updated["terminal_status"] = "completed"
    updated["result"] = result
    updated["phase"] = "completed"
    return updated


async def _ensure_task_outcome_readback(
    *,
    task_service: object,
    task_id: str,
    completion_envelope: dict,
    verification_result: dict,
) -> None:
    get_outcome = getattr(task_service, "get_task_outcome", None)
    if callable(get_outcome) and isinstance(get_outcome(task_id), dict):
        return
    recorder = getattr(task_service, "_record_task_outcome", None)
    get_task = getattr(task_service, "get_task", None)
    if not callable(recorder) or not callable(get_task):
        raise RuntimeError("Task outcome readback failed and no outcome recorder is available")
    latest_task = get_task(task_id)
    if latest_task is None:
        raise RuntimeError(f"Task readback missing after ReAct completion: {task_id}")
    recorder(
        task=latest_task,
        result=completion_envelope,
        verification_result={
            **verification_result,
            "overall_passed": bool(verification_result.get("overall_passed", verification_result.get("passed"))),
            "strategy": verification_result.get("strategy") or "react_capability_verification",
        },
    )
    if callable(get_outcome) and isinstance(get_outcome(task_id), dict):
        return
    raise RuntimeError(f"Task outcome readback failed after ReAct completion: {task_id}")
