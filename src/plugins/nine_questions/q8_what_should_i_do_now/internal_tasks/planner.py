from __future__ import annotations

from typing import Any

from .context_builder import build_internal_task_context
from .validator import validate_internal_task_plan


EXTERNAL_EXECUTOR_TYPES = {"agent", "cli", "mcp", "external_connector", "connector"}
EXTERNAL_PREFIXES = ("agent:", "cli:", "mcp:", "external_connector:", "connector:")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_external_task(task: dict[str, Any]) -> bool:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    executor_type = _text(task.get("executor_type") or metadata.get("executor_type")).lower()
    target_id = _text(task.get("target_id") or metadata.get("target_id")).lower()
    task_scope = _text(task.get("task_scope") or metadata.get("task_scope")).lower()
    return (
        task_scope == "external"
        or executor_type in EXTERNAL_EXECUTOR_TYPES
        or target_id.startswith(EXTERNAL_PREFIXES)
    )


def _internalize_task(task: dict[str, Any], *, queue_name: str, index: int) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    normalized = dict(task)
    normalized["task_id"] = _text(task.get("task_id") or task.get("id") or f"internal-{queue_name}-{index}")
    normalized["title"] = _text(task.get("title") or task.get("task") or normalized["task_id"])
    normalized["task_scope"] = "internal"
    normalized["executor_type"] = "internal"
    normalized["metadata"] = {
        **metadata,
        "task_scope": "internal",
        "executor_type": "internal",
        "source_chain": "internal_q8",
    }
    return normalized


def build_internal_task_plan(
    *,
    question_snapshot: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]],
    priority_baseline: dict[str, Any],
    functional_objectives: list[dict[str, Any]],
    raw_task_queue: dict[str, Any],
) -> dict[str, Any]:
    context = build_internal_task_context(
        question_snapshot=question_snapshot,
        normalized_task_state=normalized_task_state,
        priority_baseline=priority_baseline,
        functional_objectives=functional_objectives,
    )
    tasks: list[dict[str, Any]] = []
    for queue_name in ("next_self_tasks", "blocked_self_tasks", "proactive_actions"):
        raw_items = raw_task_queue.get(queue_name)
        if not isinstance(raw_items, list):
            continue
        for index, item in enumerate(raw_items):
            task = item if isinstance(item, dict) else {"title": item}
            if _is_external_task(task):
                continue
            tasks.append(_internalize_task(task, queue_name=queue_name, index=index))

    plan = {
        "planner": "q8_internal_task_planner",
        "context": context,
        "tasks": tasks,
        "generated": len(tasks),
    }
    return validate_internal_task_plan(plan)
