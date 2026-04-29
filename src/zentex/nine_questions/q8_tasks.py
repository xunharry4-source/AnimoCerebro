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
from zentex.tasks.models import TaskContract, TaskPriority, TaskStatus, TaskType, ZentexTask
from zentex.tasks.verification.models import (
    VerificationStrategy,
    VerificationType,
)


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
            normalized.append(
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
            metadata = {
                "source": "nine_questions.q8",
                "session_id": session_id,
                "question_id": "q8",
                "queue_name": queue_name,
                "objective": current_mission,
                "objective_profile": objective_profile,
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
                        "status": effective_status,
                        "priority": priority,
                        "originator_id": session_id,
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
