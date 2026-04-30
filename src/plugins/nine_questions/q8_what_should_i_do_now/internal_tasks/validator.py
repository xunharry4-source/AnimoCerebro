from __future__ import annotations

from typing import Any


EXTERNAL_EXECUTOR_TYPES = {"agent", "cli", "mcp", "external_connector", "connector"}
EXTERNAL_PREFIXES = ("agent:", "cli:", "mcp:", "external_connector:", "connector:")


class Q8InternalTaskIsolationError(ValueError):
    error_code = "Q8_INTERNAL_TASK_REFERENCES_EXTERNAL_CAPABILITY"


def _text(value: Any) -> str:
    return str(value or "").strip()


def validate_internal_task_plan(plan: dict[str, Any]) -> dict[str, Any]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        raise Q8InternalTaskIsolationError("Q8 internal plan must contain a tasks array")

    failures: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        task = task if isinstance(task, dict) else {}
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        executor_type = _text(task.get("executor_type") or metadata.get("executor_type")).lower()
        target_id = _text(task.get("target_id") or metadata.get("target_id")).lower()
        task_scope = _text(task.get("task_scope") or metadata.get("task_scope")).lower()
        haystack = " ".join(
            _text(value).lower()
            for value in (
                task.get("title"),
                task.get("reason"),
                task.get("required_capability"),
                task.get("tool_id"),
            )
        )
        if (
            task_scope == "external"
            or executor_type in EXTERNAL_EXECUTOR_TYPES
            or target_id.startswith(EXTERNAL_PREFIXES)
            or any(token in haystack for token in ("cli:", "mcp:", "agent:", "external_connector:"))
        ):
            failures.append(
                {
                    "index": index,
                    "title": task.get("title"),
                    "executor_type": executor_type,
                    "target_id": target_id,
                    "task_scope": task_scope,
                }
            )

    if failures:
        raise Q8InternalTaskIsolationError(
            f"{Q8InternalTaskIsolationError.error_code}: internal Q8 plan contains external references: {failures}"
        )
    return plan
