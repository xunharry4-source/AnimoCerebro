from __future__ import annotations

from typing import Any


EXTERNAL_EXECUTOR_TYPES = {"agent", "cli", "mcp", "external_connector", "connector"}
INTERNAL_EXECUTOR_TYPES = {"internal", "internal_plugin", "cognitive_plugin", "reflection", "learning", "memory"}


class Q8ExternalTaskIsolationError(ValueError):
    error_code = "Q8_EXTERNAL_TASK_REFERENCES_INTERNAL_EXECUTOR"


def _text(value: Any) -> str:
    return str(value or "").strip()


def validate_external_task_plan(plan: dict[str, Any]) -> dict[str, Any]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        raise Q8ExternalTaskIsolationError("Q8 external plan must contain a tasks array")

    failures: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        task = task if isinstance(task, dict) else {}
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        executor_type = _text(task.get("executor_type") or metadata.get("executor_type")).lower()
        task_scope = _text(task.get("task_scope") or metadata.get("task_scope")).lower()
        if task_scope == "internal" or executor_type in INTERNAL_EXECUTOR_TYPES or executor_type not in EXTERNAL_EXECUTOR_TYPES:
            failures.append(
                {
                    "index": index,
                    "title": task.get("title"),
                    "executor_type": executor_type,
                    "task_scope": task_scope,
                }
            )

    if failures:
        raise Q8ExternalTaskIsolationError(
            f"{Q8ExternalTaskIsolationError.error_code}: external Q8 plan contains non-external executors: {failures}"
        )
    return plan
