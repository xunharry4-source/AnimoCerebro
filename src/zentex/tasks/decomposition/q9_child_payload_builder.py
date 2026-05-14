from __future__ import annotations

from typing import Any, Dict, List

from zentex.tasks.models import TaskContract, TaskStatus, TaskType
from zentex.tasks.verification.models import VerificationConfig, VerificationStrategy, VerificationType, VerifierConfig


def _q9_subtask_verification_config(*, plan_type: str, executor_type: str) -> dict[str, Any]:
    rules = [
        {"type": "required_field", "field": "actual_outcome.status"},
        {"type": "required_field", "field": "external_execution.executor_type"},
        {"type": "required_field", "field": "evidence.evidence_ref"},
    ]
    if plan_type == "external" and executor_type == "external_connector":
        rules.extend(
            [
                {"type": "enum_value", "field": "actual_outcome.status", "allowed_values": ["success"]},
                {"type": "required_field", "field": "actual_outcome.output_summary"},
                {"type": "required_field", "field": "actual_outcome.evidence_refs"},
            ]
        )
    return VerificationConfig(
        enabled=True,
        strategy=VerificationStrategy.ALL_MUST_PASS,
        verifiers=[
            VerifierConfig(
                verifier_id="q9_subtask_external_execution_evidence",
                verifier_type=VerificationType.RULE_BASED,
                required=True,
                retry_on_failure=False,
                max_retries=0,
                config={"rules": rules},
            )
        ],
        auto_trigger=True,
        fallback_action="fail",
        max_total_retries=0,
    ).model_dump(mode="json")


def build_q9_child_payload(
    *,
    q9_task: Any,
    metadata: Dict[str, Any],
    step_record: Dict[str, Any],
    index: int,
    plan_type: str,
    physical_subtask_id: str,
    previous_task_id: str,
    task_scope: Any,
    target_id: str,
    executor_type: str,
    required_capabilities: List[str],
    runtime_metadata: Dict[str, Any],
    designated_executor: str,
) -> Dict[str, Any]:
    line = step_record["line"]
    q9_verification_hint = str(step_record.get("q9_verification_hint") or step_record.get("verification_method") or "").strip()
    internal_verification_contract = (
        "g31a_executor_bound_subtask_contract: require objective physical evidence "
        "including read-after-write/readback, exit_code, stdout/stderr, hash, mtime, "
        "or persisted audit record query."
    )
    return {
        "idempotency_key": f"sub-{q9_task.task_id}-q9-{plan_type}-{index}",
        "title": str(step_record["title"])[:160],
        "task_type": TaskType.SYSTEM_ACTION if plan_type == "external" else TaskType.COGNITIVE_STEP,
        "task_scope": task_scope,
        "status": TaskStatus.ASSIGNMENT_PENDING,
        "priority": q9_task.priority,
        "originator_id": q9_task.originator_id,
        "parent_task_id": q9_task.task_id,
        "subtask_id": physical_subtask_id,
        "depends_on": [previous_task_id] if previous_task_id else [],
        "target_id": None,
        "remarks": (
            "G31A subtask generated from a Q9 blueprint. "
            "Executor was bound by TaskManagementService, not by Q9."
        ),
        "tags": list(dict.fromkeys([*q9_task.tags, "q9_subtask", f"{plan_type}_executor_bound"])),
        "metadata": {
            **runtime_metadata,
            "source": "G31A.TaskSplitter",
            "source_module": "tasks.g31a",
            "parent_source_module": "nine_questions.q9",
            "session_id": metadata.get("session_id"),
            "q9_trace_id": metadata.get("q9_trace_id"),
            "q9_plan_type": plan_type,
            "q9_blueprint_parent_task_id": q9_task.task_id,
            "q9_blueprint_step_index": index,
            "q9_blueprint_step": line,
            "q9_verification_hint": q9_verification_hint,
            "internal_verification_contract": internal_verification_contract,
            "objective": step_record["objective"],
            "acceptance_criteria": step_record["acceptance_criteria"],
            "required_resources": step_record["required_resources"],
            "assignment_status": "assignment_pending",
            "task_splitter": "G31A.TaskSplitter",
            "dependency_builder": "G31A.DependencyBuilder",
            "dependency_graph_node": {
                "task_id": "",
                "subtask_id": physical_subtask_id,
                "depends_on": [previous_task_id] if previous_task_id else [],
                "step_index": index,
                "builder": "G31A.DependencyBuilder",
            },
            "subtask_record": {
                "record_type": "SubtaskRecord",
                "registered_by": "G31A.SubtaskRegistry",
                "task_splitter": "G31A.TaskSplitter",
                "task_id": "",
                "subtask_id": physical_subtask_id,
                "parent_task_id": q9_task.task_id,
                "step_index": index,
                "initial_status": TaskStatus.ASSIGNMENT_PENDING.value,
                "status_transition": {
                    "from_status": TaskStatus.SPLIT_REQUIRED.value,
                    "to_status": TaskStatus.ASSIGNMENT_PENDING.value,
                    "transition_owner": "G31A.TaskSplitter",
                },
                "id_source": "task_service_uuid4",
                "llm_id_source": "forbidden",
            },
            "precondition_check": {
                "status": "pending",
                "checker": "G31A.PreconditionChecker",
                "target_id": None,
            },
            "q9_designated_executor": designated_executor,
            "subtask_registered_by": "G31A.SubtaskRegistry",
            "q9_executor_designation_source": "ActionPlan.required_resources" if designated_executor else "capability_registry_match",
            "q9_plugin_binding_source": "pending_g31a_validation",
            "q9_execution_parameters_source": runtime_metadata.get("q9_execution_parameters_source") or "forbidden",
        },
        "contract": TaskContract(
            expected_outcome={
                "source": "q9_blueprint_subtask",
                "plan_type": plan_type,
                "blueprint_step": line,
            },
            success_criteria=[
                "Subtask executes through the task-center assigned executor.",
                "Execution result is recorded as task outcome evidence.",
                "G31A verifies execution with read-after-write/readback evidence, exit_code/stdout/stderr, hash, mtime, or persisted audit records.",
            ],
            acceptance_conditions=[
                "target_id is concrete",
                "required_capabilities are present or a query-visible G9 resource-gap negotiation is persisted.",
                "task outcome evidence contains objective physical proof such as read-after-write, exit_code, stdout/stderr, hash, mtime, or audit record readback.",
            ],
            verification_method=q9_verification_hint,
            verification=_q9_subtask_verification_config(plan_type=plan_type, executor_type=executor_type),
        ),
    }


__all__ = ["build_q9_child_payload"]
