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
        target_id = _text(task.get("target_id") or metadata.get("target_id"))
        capabilities = task.get("required_capabilities") or metadata.get("required_capabilities")
        has_capabilities = isinstance(capabilities, list) and bool([item for item in capabilities if _text(item)])
        missing_executor_detail = not target_id or not has_capabilities
        if (
            task_scope == "internal"
            or executor_type in INTERNAL_EXECUTOR_TYPES
            or executor_type not in EXTERNAL_EXECUTOR_TYPES
            or missing_executor_detail
        ):
            failures.append(
                {
                    "index": index,
                    "title": task.get("title"),
                    "executor_type": executor_type,
                    "task_scope": task_scope,
                    "target_id": target_id,
                    "has_capabilities": has_capabilities,
                }
            )

    if failures:
        raise Q8ExternalTaskIsolationError(
            f"{Q8ExternalTaskIsolationError.error_code}: external Q8 plan contains non-external executors: {failures}"
        )
    return plan
