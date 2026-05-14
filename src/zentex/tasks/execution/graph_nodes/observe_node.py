from __future__ import annotations

from zentex.tasks.execution.graph_state import ExecutionGraphState, with_failure
from zentex.tasks.execution.observation import observe_attempt
from zentex.tasks.execution.persistence import append_graph_node_io


async def observe_node(state: ExecutionGraphState) -> ExecutionGraphState:
    runtime = state.get("runtime") or {}
    attempt = state.get("current_attempt") if isinstance(state.get("current_attempt"), dict) else {}
    if not attempt:
        return with_failure(state, phase="observation_failed", failure_type="observation_failed", failure_code="ACTION_ATTEMPT_MISSING", message="No action attempt available for observation", retryable=False)
    observation = observe_attempt(context=state.get("context") or {}, attempt=attempt, runtime=runtime)
    observations = list(state.get("observations") or [])
    observations.append(observation)
    updated: ExecutionGraphState = dict(state)
    updated["observations"] = observations
    updated["phase"] = "execution_check_after_pending"
    append_graph_node_io(
        task_dao=runtime.get("task_dao"),
        task_id=str(state.get("task_id")),
        run_id=str(state.get("run_id")),
        node_id="observe",
        node_type="observe",
        status="passed",
        input_payload={"attempt_id": attempt.get("attempt_id")},
        output_payload={"observation_id": observation.get("observation_id"), "evidence_refs": observation.get("evidence_refs") or []},
        evidence_refs=observation.get("evidence_refs") or [],
    )
    return updated
