from __future__ import annotations

from typing import Any


BLOCKED_INTERNAL_KEYS = {
    "internal_plugins",
    "reflection_strategy",
    "learning_strategy",
    "memory_strategy",
    "scoring_rules",
    "available_cognitive_tools",
    "functional_objectives",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_external_task_context(*, question_snapshot: dict[str, Any]) -> dict[str, Any]:
    q3 = _dict(question_snapshot.get("q3"))
    q4 = _dict(question_snapshot.get("q4"))
    q5 = _dict(question_snapshot.get("q5"))
    q6 = _dict(question_snapshot.get("q6"))
    return {
        "context_type": "q8_external_task_context",
        "external_capabilities": {
            "functional_plugins": _list(q3.get("functional_plugins")) or _list(_dict(question_snapshot.get("q2")).get("functional_plugins")),
            "execution_tools": _list(q3.get("available_execution_tools")),
            "connected_agents": _list(q3.get("connected_agents")),
            "cli_tools": _list(q3.get("cli_tools")),
            "mcp_servers": _list(q3.get("mcp_servers")),
            "external_connectors": _list(q3.get("external_connectors")),
            "capability_upper_limits": _list(q4.get("capability_upper_limits")),
        },
        "external_constraints": {
            "allowed_action_space": _list(q5.get("allowed_action_space")),
            "forbidden_action_space": _list(q5.get("forbidden_action_space")),
            "absolute_red_lines": _list(q6.get("absolute_red_lines")),
        },
    }
