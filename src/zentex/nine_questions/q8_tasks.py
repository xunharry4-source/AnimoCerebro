from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from zentex.nine_questions.q8_evaluation_planner import (
    apply_evaluation_profile_to_task_priority,
    derive_q8_evaluation_plan,
)
from zentex.nine_questions.q8_phase_b_realtime_gate import (
    evaluate_q8_phase_b_realtime_task_gate,
    resolve_phase_b_realtime_gate_config,
)
from zentex.tasks.models import TaskContract, TaskPriority, TaskScope, TaskStatus, TaskType, ZentexTask
from zentex.tasks.verification.models import (
    VerificationStrategy,
    VerificationType,
)
from plugins.nine_questions.q8_what_should_i_do_now.external_tasks import build_external_task_plan
from plugins.nine_questions.q8_what_should_i_do_now.internal_tasks import build_internal_task_plan


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dict_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def normalize_q8_task_rows(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("task") or item.get("task_id") or item.get("id") or "").strip()
            if not title:
                continue
            normalized_item = dict(item)
            normalized_item.update(
                {
                    "task_id": str(item.get("task_id") or item.get("id") or f"q8-task-{index}"),
                    "title": title,
                    "reason": str(item.get("reason") or "").strip(),
                    "priority": item.get("priority"),
                    "expected_outcome": _dict_value(item.get("expected_outcome")),
                    "success_criteria": _string_list(item.get("success_criteria")),
                    "acceptance_conditions": _string_list(item.get("acceptance_conditions")),
                    "verification_method": str(item.get("verification_method") or "").strip(),
                    "risk_assessment": _dict_value(item.get("risk_assessment")),
                    "pause_conditions": _string_list(item.get("pause_conditions")),
                    "escalation_conditions": _string_list(item.get("escalation_conditions")),
                }
            )
            normalized.append(normalized_item)
        else:
            title = str(item or "").strip()
            if title:
                normalized.append(
                    {
                        "task_id": f"q8-task-{index}",
                        "title": title,
                        "reason": "",
                        "priority": None,
                        "expected_outcome": {},
                        "success_criteria": [],
                        "acceptance_conditions": [],
                        "verification_method": "",
                        "risk_assessment": {},
                        "pause_conditions": [],
                        "escalation_conditions": [],
                    }
                )
    return normalized


def stable_task_suffix(task: dict[str, Any], index: int) -> str:
    base = str(task.get("task_id") or task.get("title") or index).strip().lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in base)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:64] or f"task-{index}"


def coerce_task_priority(value: object, default_priority: TaskPriority) -> TaskPriority:
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
        }
        return mapping.get(normalized, default_priority)
    if isinstance(value, int):
        if value >= 90:
            return TaskPriority.CRITICAL
        if value >= 70:
            return TaskPriority.HIGH
        if value >= 40:
            return TaskPriority.MEDIUM
        return TaskPriority.LOW
    return default_priority


def _task_executor_type(task: dict[str, Any]) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return str(task.get("executor_type") or metadata.get("executor_type") or "").strip().lower()


def _task_scope(task: dict[str, Any]) -> TaskScope:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    explicit_scope = str(task.get("task_scope") or metadata.get("task_scope") or "").strip().lower()
    if explicit_scope == TaskScope.EXTERNAL.value:
        return TaskScope.EXTERNAL
    executor_type = _task_executor_type(task)
    target_id = str(task.get("target_id") or metadata.get("target_id") or "").strip().lower()
    if executor_type in {"agent", "cli", "mcp", "external_connector", "connector"}:
        return TaskScope.EXTERNAL
    if target_id.startswith(("agent:", "cli:", "mcp:", "external_connector:", "connector:")):
        return TaskScope.EXTERNAL
    return TaskScope.INTERNAL


def _queue_with_rows(task_queue: dict[str, Any], replacements: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "next_self_tasks": replacements.get("next_self_tasks", []),
        "blocked_self_tasks": replacements.get("blocked_self_tasks", []),
        "proactive_actions": replacements.get("proactive_actions", []),
        **{
            key: value
            for key, value in task_queue.items()
            if key not in {"next_self_tasks", "blocked_self_tasks", "proactive_actions"}
        },
    }


def build_q8_separated_task_plan(
    *,
    snapshot_map: dict[str, dict[str, Any]],
    objective_profile: dict[str, Any],
    task_queue: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]] | None = None,
    priority_baseline: dict[str, Any] | None = None,
    functional_objectives: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    q8_snapshot = snapshot_map.get("q8") if isinstance(snapshot_map.get("q8"), dict) else {}
    context_updates = q8_snapshot.get("context_updates") if isinstance(q8_snapshot.get("context_updates"), dict) else {}
    question_snapshot = (
        context_updates.get("q8_q1_q7_snapshot")
        or context_updates.get("q1_q7_snapshot")
        or context_updates.get("q8_objective_and_queue", {}).get("q1_q7_snapshot")
        or {}
    )
    question_snapshot = question_snapshot if isinstance(question_snapshot, dict) else {}
    priority = priority_baseline if isinstance(priority_baseline, dict) else {}
    functional = functional_objectives if isinstance(functional_objectives, list) else []
    task_state = normalized_task_state if isinstance(normalized_task_state, dict) else {}

    internal_queue_rows: dict[str, list[dict[str, Any]]] = {}
    external_queue_rows: dict[str, list[dict[str, Any]]] = {}
    for queue_name in ("next_self_tasks", "blocked_self_tasks", "proactive_actions"):
        internal_queue_rows[queue_name] = []
        external_queue_rows[queue_name] = []
        for item in normalize_q8_task_rows(task_queue.get(queue_name)):
            item = dict(item)
            item.setdefault("metadata", {})
            if _task_scope(item) == TaskScope.EXTERNAL:
                item["task_scope"] = TaskScope.EXTERNAL.value
                item["metadata"] = {
                    **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                    "task_scope": TaskScope.EXTERNAL.value,
                    "source_chain": "external_q8",
                }
                external_queue_rows[queue_name].append(item)
            else:
                item["task_scope"] = TaskScope.INTERNAL.value
                item["executor_type"] = "internal"
                item["metadata"] = {
                    **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                    "task_scope": TaskScope.INTERNAL.value,
                    "executor_type": "internal",
                    "source_chain": "internal_q8",
                }
                internal_queue_rows[queue_name].append(item)

    internal_queue = _queue_with_rows(task_queue, internal_queue_rows)
    external_queue = _queue_with_rows(task_queue, external_queue_rows)
    internal_plan = build_internal_task_plan(
        question_snapshot=question_snapshot,
        normalized_task_state=task_state,
        priority_baseline=priority,
        functional_objectives=functional,
        raw_task_queue=internal_queue,
    )
    external_plan = build_external_task_plan(
        question_snapshot=question_snapshot,
        raw_task_queue=external_queue,
    )
    return {
        "objective_profile": objective_profile,
        "internal": internal_plan,
        "external": external_plan,
        "internal_queue": internal_queue,
        "external_queue": external_queue,
        "combined_queue": _queue_with_rows(
            task_queue,
            {
                key: internal_queue_rows[key] + external_queue_rows[key]
                for key in ("next_self_tasks", "blocked_self_tasks", "proactive_actions")
            },
        ),
    }


def build_q8_task_contract(
    task: dict[str, Any],
    objective_profile: dict[str, Any],
) -> TaskContract:
    title = str(task.get("title") or "").strip()
    completion_conditions = _string_list(objective_profile.get("completion_conditions"))
    pause_conditions = list(
        dict.fromkeys(
            _string_list(task.get("pause_conditions"))
            + _string_list(objective_profile.get("pause_conditions"))
        )
    )
    escalation_conditions = list(
        dict.fromkeys(
            _string_list(task.get("escalation_conditions"))
            + _string_list(objective_profile.get("escalation_conditions"))
        )
    )
    success_criteria = _string_list(task.get("success_criteria"))
    fallback_generated = False
    if not success_criteria:
        success_criteria = completion_conditions or ([f"完成任务: {title}"] if title else [])
        fallback_generated = True

    acceptance_conditions = _string_list(task.get("acceptance_conditions")) or success_criteria
    expected_outcome = _dict_value(task.get("expected_outcome")) or {
        "summary": title,
        "source": "q8_task_contract_fallback",
    }

    risk_assessment = _dict_value(task.get("risk_assessment"))
    if fallback_generated:
        risk_assessment = {
            **risk_assessment,
            "acceptance_fallback_generated": True,
        }

    return TaskContract(
        expected_outcome=expected_outcome,
        success_criteria=success_criteria,
        acceptance_conditions=acceptance_conditions,
        verification_method=str(task.get("verification_method") or "rule_based_outcome_contract"),
        risk_assessment=risk_assessment,
        pause_conditions=pause_conditions,
        escalation_conditions=escalation_conditions,
        verification={
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "q8_required_outcome_evidence",
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


def sync_task_record_fields(
    task_service: Any,
    task: ZentexTask,
    *,
    title: str,
    remarks: str,
    priority: TaskPriority,
    tags: list[str],
    metadata: dict[str, Any],
    contract: TaskContract | None = None,
) -> None:
    task.title = title
    task.remarks = remarks
    task.priority = priority
    task.tags = list(tags)
    task.metadata = dict(metadata)
    if contract is not None:
        task.contract = contract
    task.last_updated_at = datetime.now(timezone.utc)
    if hasattr(task_service, "_shared_tasks"):
        task_service._shared_tasks.set(task.task_id, task)
    sync_fn = getattr(task_service, "_sync_task_to_database", None)
    if callable(sync_fn):
        sync_fn(task)


async def sync_q8_tasks_to_task_service(
    *,
    task_service: Any,
    session_id: str,
    snapshot_map: dict[str, dict[str, Any]],
    logger: Optional[Any] = None,
) -> None:
    if task_service is None:
        return

    q8_snapshot = snapshot_map.get("q8")
    if not isinstance(q8_snapshot, dict):
        return

    context_updates = q8_snapshot.get("context_updates")
    context_updates = context_updates if isinstance(context_updates, dict) else {}
    result_payload = q8_snapshot.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}

    objective_profile = (
        context_updates.get("q8_objective_profile")
        or result_payload.get("objective_profile")
        or {}
    )
    objective_profile = objective_profile if isinstance(objective_profile, dict) else {}
    task_queue = (
        context_updates.get("q8_task_queue")
        or result_payload.get("task_queue")
        or {}
    )
    task_queue = task_queue if isinstance(task_queue, dict) else {}
    separated_plan = build_q8_separated_task_plan(
        snapshot_map=snapshot_map,
        objective_profile=objective_profile,
        task_queue=task_queue,
        normalized_task_state=context_updates.get("q8_persistent_task_state")
        if isinstance(context_updates.get("q8_persistent_task_state"), dict)
        else None,
        priority_baseline=context_updates.get("q8_priority_baseline")
        if isinstance(context_updates.get("q8_priority_baseline"), dict)
        else None,
        functional_objectives=context_updates.get("q8_functional_objectives")
        if isinstance(context_updates.get("q8_functional_objectives"), list)
        else None,
    )
    task_queue = separated_plan["combined_queue"]

    current_mission = str(
        objective_profile.get("current_mission")
        or objective_profile.get("current_primary_objective")
        or q8_snapshot.get("summary")
        or "Q8 generated task"
    ).strip()

    queue_specs = [
        ("next_self_tasks", TaskStatus.TODO, TaskPriority.HIGH),
        ("blocked_self_tasks", TaskStatus.BLOCKED, TaskPriority.MEDIUM),
        ("proactive_actions", TaskStatus.TODO, TaskPriority.MEDIUM),
    ]
    evaluation_plan = derive_q8_evaluation_plan(snapshot_map)
    phase_b_realtime_gate_config = resolve_phase_b_realtime_gate_config(
        _dict_value(
            context_updates.get("phase_b_realtime_gate")
            or result_payload.get("phase_b_realtime_gate")
        )
    )

    existing_tasks = []
    list_tasks_fn = getattr(task_service, "list_tasks", None)
    if callable(list_tasks_fn):
        existing_tasks = list(list_tasks_fn() or [])
    existing_by_key: dict[str, ZentexTask] = {}
    for task in existing_tasks:
        metadata = getattr(task, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        if metadata.get("source") == "nine_questions.q8" and metadata.get("session_id") == session_id:
            existing_by_key[str(task.idempotency_key)] = task

    desired_keys: set[str] = set()

    for queue_name, target_status, default_priority in queue_specs:
        for index, item in enumerate(normalize_q8_task_rows(task_queue.get(queue_name))):
            suffix = stable_task_suffix(item, index)
            idempotency_key = f"nineq:{session_id}:q8:{queue_name}:{suffix}"
            desired_keys.add(idempotency_key)

            reason = str(item.get("reason") or "").strip()
            remarks = current_mission
            if reason:
                remarks = f"{current_mission}\n阻塞/说明: {reason}"
            base_priority = coerce_task_priority(item.get("priority"), default_priority)
            priority_decision = apply_evaluation_profile_to_task_priority(
                task=item,
                base_priority=base_priority,
                evaluation_plan=evaluation_plan,
            )
            item_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            scope = _task_scope(item)
            executor_type = _task_executor_type(item)
            if scope == TaskScope.INTERNAL:
                executor_type = "internal"
            target_id = str(item.get("target_id") or item_metadata.get("target_id") or "").strip()
            metadata = {
                "source": "nine_questions.q8",
                "session_id": session_id,
                "question_id": "q8",
                "queue_name": queue_name,
                "task_scope": scope.value,
                "executor_type": executor_type,
                "source_chain": "external_q8" if scope == TaskScope.EXTERNAL else "internal_q8",
                "target_id": target_id,
                "objective": current_mission,
                "objective_profile": objective_profile,
                "q8_separated_task_plan": {
                    "internal_generated": separated_plan["internal"]["generated"],
                    "external_generated": separated_plan["external"]["generated"],
                },
                "evaluation_profile": evaluation_plan.evaluation_profile,
                "phase_a_evaluation": priority_decision.metadata,
                "completion_conditions": _string_list(objective_profile.get("completion_conditions")),
                "pause_conditions": _string_list(objective_profile.get("pause_conditions")),
                "escalation_conditions": _string_list(objective_profile.get("escalation_conditions")),
                "expected_outcome": _dict_value(item.get("expected_outcome")),
                "success_criteria": _string_list(item.get("success_criteria")),
                "acceptance_conditions": _string_list(item.get("acceptance_conditions")),
                "verification_method": str(item.get("verification_method") or "").strip(),
                "risk_assessment": _dict_value(item.get("risk_assessment")),
                "trace_id": str(q8_snapshot.get("trace_id") or ""),
            }
            tags = ["nine-questions", "q8", queue_name]
            priority = priority_decision.priority
            effective_status = target_status
            if phase_b_realtime_gate_config["enabled"]:
                phase_b_decision = evaluate_q8_phase_b_realtime_task_gate(
                    task=item,
                    target_status=target_status,
                    base_priority=priority,
                    accept_threshold=phase_b_realtime_gate_config["accept_threshold"],
                    reject_threshold=phase_b_realtime_gate_config["reject_threshold"],
                )
                priority = phase_b_decision.final_priority
                effective_status = phase_b_decision.final_status
                metadata["phase_b_realtime_gate"] = phase_b_decision.to_metadata()
            contract = build_q8_task_contract(item, objective_profile)
            existing = existing_by_key.get(idempotency_key)
            if existing is not None:
                if existing.status != effective_status:
                    try:
                        await task_service.update_task_status(existing.task_id, effective_status, remarks)
                    except Exception:
                        if logger is not None:
                            logger.warning(
                                "Failed to update synced Q8 task status",
                                extra={"task_id": existing.task_id, "queue_name": queue_name},
                            )
                sync_task_record_fields(
                    task_service,
                    existing,
                    title=str(item["title"]),
                    remarks=remarks,
                    priority=priority,
                    tags=tags,
                    metadata=metadata,
                    contract=contract,
                )
                continue

            create_task_fn = getattr(task_service, "create_task", None)
            if callable(create_task_fn):
                await create_task_fn(
                    {
                        "idempotency_key": idempotency_key,
                        "title": str(item["title"]),
                        "task_type": TaskType.COGNITIVE_STEP,
                        "task_scope": scope,
                        "status": effective_status,
                        "priority": priority,
                        "originator_id": session_id,
                        "target_id": target_id or None,
                        "remarks": remarks,
                        "tags": tags,
                        "metadata": metadata,
                        "contract": contract,
                    }
                )

    for idempotency_key, task in existing_by_key.items():
        if idempotency_key in desired_keys:
            continue
        if task.status in {TaskStatus.TODO, TaskStatus.BLOCKED, TaskStatus.SUSPENDED, TaskStatus.DONE}:
            try:
                await task_service.update_task_status(
                    task.task_id,
                    TaskStatus.ARCHIVED,
                    remarks="Archived because Q8 regenerated a new task set.",
                )
            except Exception:
                if logger is not None:
                    logger.warning("Failed to archive stale Q8 synced task", extra={"task_id": task.task_id})
