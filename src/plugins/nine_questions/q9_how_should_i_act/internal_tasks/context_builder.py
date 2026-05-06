from __future__ import annotations

from typing import Any


BLOCKED_EXTERNAL_KEYS = {
    "agent",
    "agents",
    "available_execution_tools",
    "cli",
    "cli_tools",
    "connected_agents",
    "external_connector",
    "external_connectors",
    "mcp",
    "mcp_servers",
    "registered_cli_tools",
    "registered_mcp_servers",
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


def _internal_list(value: Any) -> list[Any]:
    return [item for item in _list(value) if not _is_external_value(item)]


def _abstract_capability(value: Any) -> str:
    text = str(value.get("capability") if isinstance(value, dict) else value or "").strip()
    if not text and isinstance(value, dict):
        text = str(value.get("name") or value.get("plugin_id") or "").strip()
    lower = text.lower()
    lower = lower.removeprefix("cognitive plugin:").strip()
    lower = lower.removeprefix("认知插件：").strip()
    lower = lower.removesuffix("_plugin")
    lower = lower.removesuffix("-plugin")
    if "cluster" in lower or "聚类" in lower:
        return "semantic_clustering"
    if "sandbox" in lower or "沙盒" in lower:
        return "sandbox_simulation"
    if "reflection" in lower or "反思" in lower:
        return "reflective_analysis"
    if "learning" in lower or "lesson" in lower or "学习" in lower:
        return "lesson_extraction"
    if "memory" in lower or "记忆" in lower:
        return "memory_retrieval"
    return lower.replace(" ", "_")


def _asset_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("plugin_id", "name", "organ_id", "capability"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return str(value or "").strip()


def _cognitive_assets(q1_q8: dict[str, Any]) -> list[str]:
    q2 = _dict(q1_q8.get("q2"))
    candidates = (
        q2.get("cognitive_plugins")
        or q2.get("available_cognitive_tools")
        or q2.get("internal_cognitive_plugins")
        or q2.get("cognitive_capabilities")
        or []
    )
    assets = [_asset_name(value) for value in _internal_list(candidates)]
    assets.extend(["内部记忆检索能力", "内部反思分析能力", "内部学习提炼能力", "内部推演能力"])
    return list(dict.fromkeys(item for item in assets if item))


def _cognitive_capabilities_abstract(q1_q8: dict[str, Any]) -> list[str]:
    q2 = _dict(q1_q8.get("q2"))
    candidates = (
        q2.get("cognitive_capabilities_abstract")
        or q2.get("cognitive_capabilities")
        or q2.get("cognitive_plugins")
        or q2.get("available_cognitive_tools")
        or q2.get("internal_cognitive_plugins")
        or []
    )
    return list(dict.fromkeys(item for item in (_abstract_capability(value) for value in _internal_list(candidates)) if item))


def build_internal_task_context(
    *,
    q1_q8: dict[str, Any],
    posture_baseline: dict[str, Any],
    self_model: dict[str, Any],
    reasoning_budget: dict[str, Any],
) -> dict[str, Any]:
    q1 = _dict(q1_q8.get("q1"))
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
        "context_type": "q9_internal_task_context",
        "Q1_Environment": {
            "workspace_state": q1,
            "internal_static_resources": _list(q1.get("internal_static_resources") or q1.get("static_resources")),
            "static_resource_distribution": q1.get("static_resource_distribution"),
            "static_resource_notes": q1.get("static_resource_notes") or q1.get("resource_notes"),
            "uncertainty_blind_spots": _list(q1.get("uncertainty_blind_spots") or q1.get("blind_spots")),
        },
        "Q8_Tasks": _list(q8.get("internal_cognitive_tasks")),
        "Q8_Internal_Intents": _list(q8.get("internal_cognitive_tasks")),
        "Q2_Assets": _cognitive_assets(q1_q8),
        "Q3_Role_IdentityKernel": {
            "role": q3,
            "identity_kernel": _dict(q3.get("identity_kernel")),
            "identity_anchors": _list(q3.get("identity_anchors") or q3.get("role_anchors")),
        },
        "Q2_Cognitive_Capabilities_Abstract": _cognitive_capabilities_abstract(q1_q8),
        "Q1_Environment_Q3_Role": {
            "q1_environment": q1,
            "q3_role": q3,
        },
        "Brain_Organ_States": {
            "MemoryEngine": _dict(self_model.get("memory_engine")),
            "ReflectionEngine": _dict(self_model.get("reflection_engine")),
            "LearningEngine": _dict(self_model.get("learning_engine")),
            "EvolutionEngine": _dict(self_model.get("evolution_engine")),
            "ThoughtSandbox": _dict(self_model.get("thought_sandbox")),
            "self_model": self_model,
            "reasoning_budget": reasoning_budget,
        },
        "objective": {
            "current_mission": q8.get("current_mission"),
            "current_phase_tasks": _list(q8.get("current_phase_tasks")),
            "priority_order": _list(q8.get("priority_order")),
        },
        "internal_capabilities": {
            "verified_capabilities": _internal_list(q4.get("verified_capabilities")),
            "actionable_space": _internal_list(q4.get("actionable_space")),
            "role_context": baseline.get("role_context"),
            "evaluation_style": baseline.get("evaluation_style"),
        },
        "internal_runtime": {
            "self_model": self_model,
            "reasoning_budget": reasoning_budget,
            "allowed_directions": _list(evolution.get("allowed_directions")),
            "validation_requirements": _list(evolution.get("validation_requirements")),
        },
        "constraints": {
            "forbidden_action_space": _list(q5.get("forbidden_action_space")),
            "absolute_red_lines": _list(q6.get("absolute_red_lines")),
            "non_bypassable_constraints": _list(q7.get("non_bypassable_constraints")),
            "pause_conditions": _list(escalation.get("pause_conditions")),
            "confirmation_required_conditions": _list(escalation.get("confirmation_required_conditions")),
        },
    }
