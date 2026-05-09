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
    q7 = _dict(question_snapshot.get("q7"))
    return {
        "context_type": "q8_external_task_context",
        "external_capabilities": {
            "functional_plugins": _list(q3.get("functional_plugins")) or _list(_dict(question_snapshot.get("q2")).get("functional_plugins")),
            "execution_tools": _list(q3.get("available_execution_tools")),
            "connected_agents": _list(q3.get("connected_agents")),
            "cli_tools": _list(q3.get("cli_tools")),
            "mcp_servers": _list(q3.get("mcp_servers")),
            "external_connectors": _list(q3.get("external_connectors")),
        },
        "external_constraints": {
            "source": "q7_external_public_output",
            "external_creative_possibilities": _list(q7.get("external_creative_possibilities")),
            "ready_for_q4_objective_candidates": _list(q7.get("ready_for_q4_objective_candidates")),
            "needs_registration_possibilities": _list(q7.get("needs_registration_possibilities")),
            "possibility_statuses": _list(q7.get("possibility_statuses")),
            "non_bypassable_constraints": _list(q7.get("non_bypassable_constraints")),
        },
    }
