from __future__ import annotations

from typing import Any


BLOCKED_INTERNAL_KEYS = {
    "available_cognitive_tools",
    "cognitive_tools",
    "internal_plugins",
    "learning_strategy",
    "memory_strategy",
    "reflection_strategy",
    "self_model",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_external_value(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return any(
        token in text
        for token in (
            "agent:",
            "cli:",
            "connector:",
            "external execution",
            "external_executor",
            "external_tool",
            "external_connector:",
            "http",
            "mcp:",
            "network",
            "workspace write",
            "write file",
            "外部",
            "连接器",
            "命令行",
        )
    )


def _external_list(value: Any) -> list[Any]:
    return [item for item in _list(value) if _is_external_value(item)]


def _functional_plugins(q1_q8: dict[str, Any]) -> list[Any]:
    q2 = _dict(q1_q8.get("q2"))
    candidates = (
        q2.get("functional_plugins")
        or q2.get("external_functional_plugins")
        or q2.get("available_execution_tools")
        or []
    )
    return _external_list(candidates) or _list(candidates)


def _asset_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("plugin_id", "name", "tool_name", "connector_id", "agent_id", "id"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return str(value or "").strip()


def _functional_assets(q1_q8: dict[str, Any]) -> list[str]:
    q2 = _dict(q1_q8.get("q2"))
    candidates: list[Any] = []
    for key in ("functional_plugins", "external_functional_plugins", "available_execution_tools", "cli_tools", "mcp_servers", "external_agents"):
        candidates.extend(_list(q2.get(key)))
    return list(dict.fromkeys(item for item in (_asset_name(value) for value in candidates) if item))


def build_external_task_context(
    *,
    q1_q8: dict[str, Any],
    posture_baseline: dict[str, Any],
) -> dict[str, Any]:
    q1 = _dict(q1_q8.get("q1"))
    q2 = _dict(q1_q8.get("q2"))
    q3 = _dict(q1_q8.get("q3"))
    q4 = _dict(q1_q8.get("q4"))
    q5 = _dict(q1_q8.get("q5"))
    q6 = _dict(q1_q8.get("q6"))
    q7 = _dict(q1_q8.get("q7"))
    q8 = _dict(q1_q8.get("q8"))
    baseline = _dict(posture_baseline.get("evaluation_profile"))
    evolution = _dict(posture_baseline.get("evolution_profile"))
    escalation = _dict(posture_baseline.get("escalation_profile"))
    return {
        "context_type": "q9_external_task_context",
        "Q1_Environment": {
            "host_state": q1,
            "workspace_topology": q1.get("workspace_topology"),
            "internal_static_resources": _list(q1.get("internal_static_resources") or q1.get("static_resources")),
            "static_resource_absolute_paths": _list(q1.get("static_resource_absolute_paths") or q1.get("absolute_paths")),
            "static_resource_notes": q1.get("static_resource_notes") or q1.get("resource_notes"),
        },
        "Q8_Tasks": _list(q8.get("external_execution_tasks")),
        "Q8_External_Tasks": _list(q8.get("external_execution_tasks")),
        "Q2_Assets": _functional_assets(q1_q8),
        "Q2_Functional_Assets": _functional_assets(q1_q8),
        "Q2_Functional_Plugins": _functional_plugins(q1_q8),
        "Q3_Role_IdentityKernel": {
            "role": q3,
            "identity_kernel": _dict(q3.get("identity_kernel")),
            "identity_anchors": _list(q3.get("identity_anchors") or q3.get("role_anchors")),
        },
        "Q4_External_Capabilities": {
            "verified_capabilities": _external_list(q4.get("verified_capabilities")),
            "capability_upper_limits": _list(q4.get("capability_upper_limits")),
            "functional_plugins": _list(q2.get("functional_plugins")),
            "cli_tools": _list(q2.get("cli_tools")),
            "mcp_servers": _list(q2.get("mcp_servers")),
            "external_agents": _list(q2.get("external_agents")),
        },
        "Q7_Redlines": {
            "current_red_line_hits": _list(q7.get("current_red_line_hits")),
            "non_bypassable_constraints": _list(q7.get("non_bypassable_constraints")),
        },
        "objective": {
            "current_mission": q8.get("current_mission"),
            "priority_order": _list(q8.get("priority_order")),
        },
        "external_capabilities": {
            "verified_capabilities": _external_list(q4.get("verified_capabilities")),
            "capability_upper_limits": _list(q4.get("capability_upper_limits")),
            "risk_level": baseline.get("risk_level"),
            "risk_threshold": evolution.get("risk_threshold"),
        },
        "external_constraints": {
            "allowed_action_space": _list(q5.get("allowed_action_space")),
            "forbidden_action_space": _list(q5.get("forbidden_action_space")),
            "requires_escalation_actions": _list(q5.get("requires_escalation_actions")),
            "absolute_red_lines": _list(q6.get("absolute_red_lines")),
            "current_red_line_hits": _list(q7.get("current_red_line_hits")),
            "non_bypassable_constraints": _list(q7.get("non_bypassable_constraints")),
        },
        "safety_gates": {
            "pause_conditions": _list(escalation.get("pause_conditions")),
            "confirmation_required_conditions": _list(escalation.get("confirmation_required_conditions")),
            "rollback_conditions": _list(escalation.get("rollback_conditions")),
        },
    }
