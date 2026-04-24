from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from zentex.tasks.models import TaskPriority, TaskStatus, TaskType, ZentexTask


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


def sync_task_record_fields(
    task_service: Any,
    task: ZentexTask,
    *,
    title: str,
    remarks: str,
    priority: TaskPriority,
    tags: list[str],
    metadata: dict[str, Any],
) -> None:
    task.title = title
    task.remarks = remarks
    task.priority = priority
    task.tags = list(tags)
    task.metadata = dict(metadata)
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
            metadata = {
                "source": "nine_questions.q8",
                "session_id": session_id,
                "question_id": "q8",
                "queue_name": queue_name,
                "objective": current_mission,
                "trace_id": str(q8_snapshot.get("trace_id") or ""),
            }
            tags = ["nine-questions", "q8", queue_name]
            priority = coerce_task_priority(item.get("priority"), default_priority)
            existing = existing_by_key.get(idempotency_key)
            if existing is not None:
                if existing.status != target_status:
                    try:
                        task_service.update_task_status(existing.task_id, target_status, remarks)
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
                )
                continue

            create_task_fn = getattr(task_service, "create_task", None)
            if callable(create_task_fn):
                await create_task_fn(
                    {
                        "idempotency_key": idempotency_key,
                        "title": str(item["title"]),
                        "task_type": TaskType.COGNITIVE_STEP,
                        "status": target_status,
                        "priority": priority,
                        "originator_id": session_id,
                        "remarks": remarks,
                        "tags": tags,
                        "metadata": metadata,
                    }
                )

    for idempotency_key, task in existing_by_key.items():
        if idempotency_key in desired_keys:
            continue
        if task.status in {TaskStatus.TODO, TaskStatus.BLOCKED, TaskStatus.SUSPENDED, TaskStatus.DONE}:
            try:
                task_service.update_task_status(
                    task.task_id,
                    TaskStatus.ARCHIVED,
                    remarks="Archived because Q8 regenerated a new task set.",
                )
            except Exception:
                if logger is not None:
                    logger.warning("Failed to archive stale Q8 synced task", extra={"task_id": task.task_id})
