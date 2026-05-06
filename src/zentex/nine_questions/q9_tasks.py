from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from zentex.tasks.models import TaskContract, TaskPriority, TaskScope, TaskStatus, TaskType
from zentex.tasks.verification.models import VerificationStrategy, VerificationType

logger = logging.getLogger(__name__)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _q9_result_payload(q9_snapshot: dict[str, Any]) -> dict[str, Any]:
    context_updates = _dict(q9_snapshot.get("context_updates"))
    return _dict(context_updates.get("q9_action_posture") or q9_snapshot.get("result"))


def _q9_task_handling(q9_snapshot: dict[str, Any]) -> dict[str, Any]:
    context_updates = _dict(q9_snapshot.get("context_updates"))
    result_payload = _q9_result_payload(q9_snapshot)
    legacy_handling = _dict(
        context_updates.get("q9_internal_external_task_handling")
        or result_payload.get("q9_internal_external_task_handling")
    )
    if legacy_handling:
        return legacy_handling
    internal = _dict(context_updates.get("q9_internal_task_handling") or result_payload.get("q9_internal_task_handling"))
    external = _dict(context_updates.get("q9_external_task_handling") or result_payload.get("q9_external_task_handling"))
    if not internal:
        internal = _dict(context_updates.get("internal_plan") or result_payload.get("internal_plan"))
    if not external:
        external = _dict(context_updates.get("external_plan") or result_payload.get("external_plan"))
    return {
        "internal": internal,
        "external": external,
    }


def _existing_by_idempotency_key(task_service: Any, idempotency_key: str) -> Any | None:
    list_tasks = getattr(task_service, "list_tasks", None)
    if callable(list_tasks):
        try:
            tasks = list_tasks(metadata_filters={"q9_sync_idempotency_key": idempotency_key}, limit=10, offset=0) or []
        except TypeError:
            tasks = list_tasks(limit=10, offset=0) or []
        for task in tasks:
            if _text(getattr(task, "idempotency_key", "")) == idempotency_key:
                return task
            metadata = getattr(task, "metadata", None)
            if isinstance(metadata, dict) and metadata.get("q9_sync_idempotency_key") == idempotency_key:
                return task
    get_task = getattr(task_service, "get_task", None)
    shared_idempotency = getattr(task_service, "_shared_idempotency", None)
    if callable(get_task) and shared_idempotency is not None:
        task_id = shared_idempotency.get(idempotency_key)
        if task_id:
            return get_task(task_id)
    return None


def _sync_existing_task(task_service: Any, task: Any, payload: dict[str, Any]) -> Any:
    task.title = payload["title"]
    task.remarks = payload.get("remarks")
    task.priority = payload["priority"]
    task.tags = list(payload.get("tags") or [])
    task.metadata = dict(payload.get("metadata") or {})
    task.contract = payload["contract"]
    task.last_updated_at = datetime.now(timezone.utc)
    if hasattr(task_service, "_shared_tasks"):
        task_service._shared_tasks.set(task.task_id, task)
    sync_fn = getattr(task_service, "_sync_task_to_database", None)
    if callable(sync_fn):
        sync_fn(task)
    return task


def _record_task_center_audit(
    *,
    task_service: Any,
    task_id: str,
    action: str,
    details: dict[str, Any],
) -> None:
    record_audit = getattr(task_service, "_record_audit", None)
    if callable(record_audit):
        record_audit(task_id, action, details)


def _contract_for_blueprint(*, plan_type: str, blueprint: dict[str, Any]) -> TaskContract:
    alternatives = _list(blueprint.get("candidate_alternatives"))
    expected_items = (
        _list(blueprint.get("expected_results"))
        or _list(blueprint.get("expected_internal_outcomes"))
        or _list(blueprint.get("expected_external_receipts"))
    )
    return TaskContract(
        expected_outcome={
            "source": "q9_action_blueprint",
            "plan_type": plan_type,
            "expected_items": expected_items,
        },
        success_criteria=[
            "G31A.TaskSplitter consumes the Q9 blueprint without Q9 creating concrete subtask records.",
            "G31A.ResourceMatcher validates the Q9-designated executor before binding a runtime executor.",
        ],
        acceptance_conditions=[
            "Task metadata preserves Q9 blueprint and architecture-boundary deferrals.",
            "Q9 sync preserves executor/resource designations as blueprint data only, without execution parameters.",
        ],
        verification_method="q9_blueprint_handoff_contract",
        risk_assessment={
            "plan_type": plan_type,
            "candidate_alternatives": alternatives,
        },
        pause_conditions=[
            "G31A task center unavailable",
            "Q9 blueprint missing required fallback alternatives",
        ],
        escalation_conditions=[
            "Q9 blueprint attempts to provide execution parameters or bypass G31A binding",
        ],
        verification={
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "q9_blueprint_handoff_metadata",
                    "verifier_type": VerificationType.RULE_BASED.value,
                    "retry_on_failure": False,
                    "max_retries": 0,
                    "config": {
                        "rules": [
                            {"type": "required_field", "field": "actual_outcome"},
                            {"type": "required_field", "field": "evidence"},
                        ]
                    },
                }
            ],
        },
    )


def _blueprint_task_payload(
    *,
    session_id: str,
    trace_id: str,
    plan_type: str,
    blueprint: dict[str, Any],
    action_items: list[dict[str, Any]],
    action_plan: dict[str, Any],
    q8_task_index: int | None = None,
    q8_task: Any = None,
) -> dict[str, Any]:
    scope = TaskScope.INTERNAL if plan_type == "internal" else TaskScope.EXTERNAL
    target_id = "internal:g31a_task_center" if plan_type == "internal" else "external:g31a_task_center"
    title_suffix = f" task {q8_task_index + 1}" if q8_task_index is not None else ""
    title = f"Q9 {plan_type} action blueprint handoff{title_suffix}"
    idempotency_key = (
        f"nine_questions:q9:{session_id}:{plan_type}:task:{q8_task_index}:blueprint"
        if q8_task_index is not None
        else f"nine_questions:q9:{session_id}:{plan_type}:blueprint"
    )
    return {
        "idempotency_key": idempotency_key,
        "title": title,
        "task_type": TaskType.COGNITIVE_STEP,
        "task_scope": scope,
        "status": TaskStatus.SPLIT_REQUIRED,
        "priority": TaskPriority.HIGH if plan_type == "external" else TaskPriority.MEDIUM,
        "originator_id": session_id,
        "target_id": target_id,
        "remarks": (
            "Q9 synchronized a pure cognitive action blueprint to G31A. "
            "G31A owns real subtask splitting, resource matching, scheduling, and execution binding."
        ),
        "tags": ["nine_questions", "q9", "g31a_handoff", f"{plan_type}_blueprint"],
        "metadata": {
            "source": "nine_questions.q9",
            "source_module": "nine_questions.q9",
            "session_id": session_id,
            "question_id": "q9",
            "q9_trace_id": trace_id,
            "q9_plan_type": plan_type,
            "q9_q8_task_index": q8_task_index,
            "q9_q8_task": q8_task,
            "q9_sync_idempotency_key": idempotency_key,
            "q9_action_blueprint": blueprint,
            "q9_action_items": action_items,
            "q9_action_plan": action_plan,
            "task_scope": scope.value,
            "target_id": target_id,
            "source_chain": "q9_to_g31a_task_center",
            "sync_owner": "q9",
            "sync_boundary": "blueprint_only",
            "resource_matching_deferred_to": "G31A.ResourceMatcher",
            "task_splitting_deferred_to": "G31A.TaskSplitter",
            "subtask_registry_deferred_to": "G31A.SubtaskRegistry",
            "subtask_scheduler_deferred_to": "G31A.SubtaskScheduler",
            "parameter_binding_deferred_to": "G31A",
            "executor_designation_allowed_for_q9": True,
            "executor_binding_deferred_to": "G31A.ResourceMatcher",
            "plugin_binding_forbidden_for_q9": False,
            "execution_parameters_forbidden_for_q9": True,
            "worker_dispatch_enabled": False,
        },
        "contract": _contract_for_blueprint(plan_type=plan_type, blueprint=blueprint),
    }


def _extract_blueprint_specs(q9_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    result_payload = _q9_result_payload(q9_snapshot)
    context_updates = _dict(q9_snapshot.get("context_updates"))
    handling = _q9_task_handling(q9_snapshot)
    specs: list[dict[str, Any]] = []
    internal_llm_output = _dict(
        context_updates.get("q9_internal_llm_output")
        or result_payload.get("q9_internal_llm_output")
    )
    internal_llm_input = _dict(
        context_updates.get("q9_internal_llm_input")
        or result_payload.get("q9_internal_llm_input")
    )
    internal_q8_tasks = _list(_dict(internal_llm_input.get("context")).get("Q8_Tasks"))
    internal_task_outputs = _list(internal_llm_output.get("task_outputs"))
    for index, task_output in enumerate(internal_task_outputs):
        output = _dict(task_output)
        blueprint = _dict(output.get("InternalActionPlan"))
        if not blueprint or not _list(blueprint.get("action_steps")):
            continue
        specs.append(
            {
                "plan_type": "internal",
                "blueprint": blueprint,
                "action_items": [],
                "action_plan": _dict(internal_llm_output.get("InternalActionPlan")),
                "q8_task_index": index,
                "q8_task": internal_q8_tasks[index] if index < len(internal_q8_tasks) else None,
            }
        )
    if any(spec.get("plan_type") == "internal" for spec in specs):
        internal_handling_enabled = False
    else:
        internal_handling_enabled = True
    for plan_type, wrapper_key in (("internal", "internal"),):
        if not internal_handling_enabled:
            continue
        wrapper = _dict(handling.get(wrapper_key))
        blueprint = (
            _dict(wrapper.get("ActionPlan"))
            or _dict(wrapper.get("InternalActionPlan"))
            or _dict(wrapper.get("ExternalActionPlan"))
        )
        if not blueprint:
            continue
        action_items = _list(wrapper.get("action_items"))
        has_plan = bool(
            _list(blueprint.get("current_action_plan"))
            or _list(blueprint.get("current_internal_plan"))
            or _list(blueprint.get("current_external_plan"))
            or _list(blueprint.get("action_steps"))
        )
        if not has_plan:
            continue
        specs.append(
            {
                "plan_type": plan_type,
                "blueprint": blueprint,
                "action_items": [item for item in action_items if isinstance(item, dict)],
                "action_plan": _dict(result_payload.get("action_plan")),
                "q8_task_index": None,
                "q8_task": None,
            }
        )
    external_llm_output = _dict(
        context_updates.get("q9_external_llm_output")
        or result_payload.get("q9_external_llm_output")
    )
    external_llm_input = _dict(
        context_updates.get("q9_external_llm_input")
        or result_payload.get("q9_external_llm_input")
    )
    q8_tasks = _list(_dict(external_llm_input.get("context")).get("Q8_Tasks"))
    task_outputs = _list(external_llm_output.get("task_outputs"))
    for index, task_output in enumerate(task_outputs):
        output = _dict(task_output)
        blueprint = _dict(output.get("ExternalActionPlan"))
        if not blueprint or not _list(blueprint.get("action_steps")):
            continue
        specs.append(
            {
                "plan_type": "external",
                "blueprint": blueprint,
                "action_items": [],
                "action_plan": _dict(external_llm_output.get("ExternalActionPlan")),
                "q8_task_index": index,
                "q8_task": q8_tasks[index] if index < len(q8_tasks) else None,
            }
        )
    if not any(spec.get("plan_type") == "external" for spec in specs):
        wrapper = _dict(handling.get("external"))
        blueprint = (
            _dict(wrapper.get("ActionPlan"))
            or _dict(wrapper.get("ExternalActionPlan"))
        )
        if blueprint and (
            _list(blueprint.get("current_action_plan"))
            or _list(blueprint.get("current_external_plan"))
            or _list(blueprint.get("action_steps"))
        ):
            specs.append(
                {
                    "plan_type": "external",
                    "blueprint": blueprint,
                    "action_items": [item for item in _list(wrapper.get("action_items")) if isinstance(item, dict)],
                    "action_plan": _dict(result_payload.get("action_plan")),
                    "q8_task_index": None,
                    "q8_task": None,
                }
            )
    return specs


async def sync_q9_tasks_to_task_service(
    *,
    task_service: Any,
    session_id: str,
    snapshot_map: dict[str, dict[str, Any]],
    logger: Any | None = None,
) -> list[Any]:
    if task_service is None:
        return []
    q9_snapshot = _dict(snapshot_map.get("q9"))
    if not q9_snapshot:
        return []

    trace_id = _text(q9_snapshot.get("trace_id") or _q9_result_payload(q9_snapshot).get("trace_id"))
    synced: list[Any] = []
    active_logger = logger if logger is not None else logging.getLogger(__name__)
    for spec in _extract_blueprint_specs(q9_snapshot):
        payload = _blueprint_task_payload(
            session_id=session_id,
            trace_id=trace_id,
            plan_type=spec["plan_type"],
            blueprint=spec["blueprint"],
            action_items=spec["action_items"],
            action_plan=spec["action_plan"],
            q8_task_index=spec.get("q8_task_index"),
            q8_task=spec.get("q8_task"),
        )
        existing = _existing_by_idempotency_key(task_service, payload["idempotency_key"])
        reused_existing = existing is not None
        if existing is not None:
            parent_task = _sync_existing_task(task_service, existing, payload)
            synced.append(parent_task)
        else:
            create_task = getattr(task_service, "create_task", None)
            if not callable(create_task):
                continue
            parent_task = await create_task(payload)
            if parent_task is None:
                raise RuntimeError(
                    "Q9 task-center sync failed: task_service.create_task returned None "
                    f"for idempotency_key={payload['idempotency_key']} plan_type={spec['plan_type']} "
                    f"q8_task_index={spec.get('q8_task_index')}"
                )
            synced.append(parent_task)

        audit_details = {
            "event": "q9_blueprint_received_by_task_center",
            "session_id": session_id,
            "q9_trace_id": trace_id,
            "plan_type": spec["plan_type"],
            "idempotency_key": payload["idempotency_key"],
            "reused_existing_task": reused_existing,
            "action_item_count": len(spec["action_items"]),
            "q8_task_index": spec.get("q8_task_index"),
            "blueprint_fields": sorted(spec["blueprint"].keys()),
            "sync_boundary": "blueprint_only",
            "task_center_responsibility": [
                "subtask_splitting",
                "resource_matching",
                "executor_binding",
                "scheduling",
            ],
        }
        _record_task_center_audit(
            task_service=task_service,
            task_id=parent_task.task_id,
            action="Q9_BLUEPRINT_RECEIVED_BY_TASK_CENTER",
            details=audit_details,
        )
        active_logger.info(
            "Q9 blueprint received by task center.",
            extra={
                "session_id": session_id,
                "q9_trace_id": trace_id,
                "task_id": parent_task.task_id,
                "plan_type": spec["plan_type"],
                "action_item_count": len(spec["action_items"]),
            },
        )

        decompose = getattr(task_service, "decompose_q9_blueprint_task", None)
        if callable(decompose):
            _record_task_center_audit(
                task_service=task_service,
                task_id=parent_task.task_id,
                action="Q9_BLUEPRINT_DECOMPOSITION_REQUESTED",
                details={
                    "event": "q9_blueprint_decomposition_requested",
                    "session_id": session_id,
                    "q9_trace_id": trace_id,
                    "plan_type": spec["plan_type"],
                    "parent_task_id": parent_task.task_id,
                },
            )
            active_logger.info(
                "Q9 blueprint decomposition requested.",
                extra={
                    "session_id": session_id,
                    "q9_trace_id": trace_id,
                    "task_id": parent_task.task_id,
                    "plan_type": spec["plan_type"],
                },
            )
            await decompose(parent_task)

    if active_logger is not None:
        active_logger.info(
            "Q9 synchronized action blueprints to task center.",
            extra={"session_id": session_id, "synced_count": len(synced)},
        )
    return synced
