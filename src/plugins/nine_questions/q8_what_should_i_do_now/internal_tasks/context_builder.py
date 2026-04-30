from __future__ import annotations

from typing import Any


BLOCKED_EXTERNAL_KEYS = {
    "cli",
    "mcp",
    "agent",
    "agents",
    "external_connector",
    "external_connectors",
    "available_execution_tools",
    "registered_cli_tools",
    "registered_mcp_servers",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_internal_task_context(
    *,
    question_snapshot: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]],
    priority_baseline: dict[str, Any],
    functional_objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    q3 = _dict(question_snapshot.get("q3"))
    q4 = _dict(question_snapshot.get("q4"))
    q5 = _dict(question_snapshot.get("q5"))
    q6 = _dict(question_snapshot.get("q6"))
    q7 = _dict(question_snapshot.get("q7"))
    return {
        "context_type": "q8_internal_task_context",
        "internal_capabilities": {
            "cognitive_tools": _list(q3.get("available_cognitive_tools")),
            "actionable_space": _list(q4.get("actionable_space")),
            "executable_strategies": _list(q4.get("executable_strategies")),
            "fallback_plans": _list(q7.get("fallback_plans")),
        },
        "internal_data": {
            "task_state": normalized_task_state,
            "functional_objectives": functional_objectives,
            "priority_baseline": priority_baseline,
        },
        "constraints": {
            "allowed_action_space": _list(q5.get("allowed_action_space")),
            "forbidden_action_space": _list(q5.get("forbidden_action_space")),
            "absolute_red_lines": _list(q6.get("absolute_red_lines")),
        },
    }
