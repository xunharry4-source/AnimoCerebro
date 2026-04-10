"""
Q3 (我有什么) evidence building and extraction.

Contains functions for building and extracting EVIDENCE_Q3 evidence.
"""

from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q3PreprocessedEvidence,
    Q3WhatDoIHaveInferenceView,
    Q3AssetRow,
    Q3AgentRow,
    Q3WorkspaceAndPermission,
    Q3ToolsAndAgents,
    Q3MemoryAndStrategy,
    Q3ResourceSufficiencyView,
)

from .helpers import _coerce_string_list


def _build_q3_preprocessed_evidence(context_payload: dict[str, Any]) -> Q3PreprocessedEvidence | None:
    unified_inventory = context_payload.get("q3_unified_asset_inventory", {})
    if not isinstance(unified_inventory, dict):
        unified_inventory = {}

    permissions_raw = context_payload.get("permissions", {})
    workspace_assets_raw = context_payload.get("workspace_assets", {})
    active_tools_raw = context_payload.get("active_tools", {})
    loaded_memories_raw = context_payload.get("loaded_memories", {})

    # 1. Workspaces & Permissions
    wp_raw = context_payload.get("workspaces_and_permissions", {})
    if not isinstance(wp_raw, dict):
        wp_raw = {}
    wp = Q3WorkspaceAndPermission(
        workspaces=(
            _coerce_string_list(unified_inventory.get("accessible_workspace_zones"))
            or _coerce_string_list((permissions_raw or {}).get("accessible_workspace_zones"))
            or _coerce_string_list((workspace_assets_raw or {}).get("accessible_workspace_zones"))
            or _coerce_string_list(wp_raw.get("available_workspaces"))
        ),
        tenant_permissions=(
            _coerce_string_list((permissions_raw or {}).get("tenant_scope"))
            or _coerce_string_list(wp_raw.get("tenant_permissions"))
        ),
        execution_tokens=(
            _coerce_string_list((permissions_raw or {}).get("brain_scope"))
            or _coerce_string_list((permissions_raw or {}).get("execution_tokens"))
            or _coerce_string_list(wp_raw.get("execution_tokens"))
        ),
    )

    # 2. Tools & Agents
    ta_raw = context_payload.get("tool_inventory", {})
    if not isinstance(ta_raw, dict):
        ta_raw = {}
    connected_agents_raw = (
        unified_inventory.get("connected_agents")
        or ta_raw.get("connected_agents")
        or context_payload.get("connected_agents")
        or []
    )
    filtered_connected_agents = []
    if isinstance(connected_agents_raw, list):
        for agent in connected_agents_raw:
            if not isinstance(agent, dict):
                continue
            if str(agent.get("status") or "").lower() == "offline":
                continue
            filtered_connected_agents.append(agent)

    def _humanize_q3_asset_row(raw_id: object) -> Q3AssetRow:
        raw_text = str(raw_id or "").strip()
        name = " ".join(chunk.capitalize() for chunk in raw_text.replace(":", " ").replace(".", " ").replace("-", " ").replace("_", " ").split()) or "未知工具"
        return Q3AssetRow(
            id=raw_text,
            name=name,
            introduction=f"{name} 是当前运行态中可调用的一项工具资产。",
            function_description=f"{name} 用于提供与 {raw_text} 对应的认知或执行能力。",
        )

    def _humanize_q3_agent_row(agent: dict[str, Any]) -> Q3AgentRow:
        agent_id = str(agent.get("agent_id") or agent.get("id") or agent.get("name") or "").strip()
        name = str(agent.get("name") or "").strip() or (
            " ".join(chunk.capitalize() for chunk in agent_id.replace("-", " ").replace("_", " ").split()) if agent_id else "未知 Agent"
        )
        introduction = str(agent.get("summary") or agent.get("description") or "").strip() or f"{name} 是当前已连接的协作 Agent。"
        function_description = (
            f"{name} 负责 {agent.get('role') or agent.get('scope') or agent.get('status')} 相关的协作支持。"
            if (agent.get("role") or agent.get("scope") or agent.get("status"))
            else f"{name} 用于承接需要多 Agent 协同的任务。"
        )
        return Q3AgentRow(
            id=agent_id or name,
            name=name,
            introduction=introduction,
            function_description=function_description,
            status=str(agent.get("status") or "").strip() or None,
        )

    humanized_inventory = context_payload.get("q3_humanized_asset_inventory", {})
    if not isinstance(humanized_inventory, dict):
        humanized_inventory = {}
    cognitive_tool_rows = [
        Q3AssetRow.model_validate(item)
        for item in (humanized_inventory.get("cognitive_tool_rows") or [])
        if isinstance(item, dict)
    ]
    if not cognitive_tool_rows:
        cognitive_tool_rows = [
            _humanize_q3_asset_row(item)
            for item in (
                _coerce_string_list(unified_inventory.get("available_cognitive_tools"))
                or _coerce_string_list((active_tools_raw or {}).get("available_cognitive_tools"))
                or _coerce_string_list(ta_raw.get("cognitive_tools"))
            )
        ]
    execution_tool_rows = [
        Q3AssetRow.model_validate(item)
        for item in (humanized_inventory.get("execution_tool_rows") or [])
        if isinstance(item, dict)
    ]
    if not execution_tool_rows:
        execution_tool_rows = [
            _humanize_q3_asset_row(item)
            for item in (
                _coerce_string_list(unified_inventory.get("available_execution_tools"))
                or _coerce_string_list((active_tools_raw or {}).get("available_execution_tools"))
                or _coerce_string_list(ta_raw.get("execution_tools"))
            )
        ]
    connected_agent_rows = [
        Q3AgentRow.model_validate(item)
        for item in (humanized_inventory.get("connected_agent_rows") or [])
        if isinstance(item, dict)
    ]
    if not connected_agent_rows:
        connected_agent_rows = [_humanize_q3_agent_row(item) for item in filtered_connected_agents]
    ta = Q3ToolsAndAgents(
        cognitive_tools=(
            _coerce_string_list(unified_inventory.get("available_cognitive_tools"))
            or _coerce_string_list((active_tools_raw or {}).get("available_cognitive_tools"))
            or _coerce_string_list(ta_raw.get("cognitive_tools"))
        ),
        execution_tools=(
            _coerce_string_list(unified_inventory.get("available_execution_tools"))
            or _coerce_string_list((active_tools_raw or {}).get("available_execution_tools"))
            or _coerce_string_list(ta_raw.get("execution_tools"))
        ),
        connected_agents=filtered_connected_agents,
        cognitive_tool_rows=cognitive_tool_rows,
        execution_tool_rows=execution_tool_rows,
        connected_agent_rows=connected_agent_rows,
    )

    # 3. Memory & Strategy
    ms_raw = context_payload.get("memory_and_strategy", {})
    if not isinstance(ms_raw, dict):
        ms_raw = {}
    ms = Q3MemoryAndStrategy(
        experience_logs=(
            _coerce_string_list((loaded_memories_raw or {}).get("experience_logs"))
            or _coerce_string_list(ms_raw.get("experience_logs"))
        ),
        strategy_patches=(
            _coerce_string_list(unified_inventory.get("activated_strategy_patches"))
            or _coerce_string_list((loaded_memories_raw or {}).get("activated_strategy_patches"))
            or _coerce_string_list(ms_raw.get("strategy_patches"))
        ),
    )

    if not wp.workspaces and not ta.cognitive_tools and not ta.execution_tools and not ms.strategy_patches and not ms.experience_logs:
        return None

    return Q3PreprocessedEvidence(
        workspace_permission=wp,
        tools_agents=ta,
        memory_strategy=ms,
    )


def _extract_q3_preprocessed_evidence(context_payload: object) -> Q3PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        k in context_payload
        for k in (
            "workspaces_and_permissions",
            "tool_inventory",
            "memory_and_strategy",
            "q3_unified_asset_inventory",
            "permissions",
            "workspace_assets",
            "active_tools",
            "loaded_memories",
            "connected_agents",
        )
    ):
        return None
    return _build_q3_preprocessed_evidence(context_payload)


def _extract_q3_inference_result(result_payload: object) -> Q3WhatDoIHaveInferenceView | None:
    if not isinstance(result_payload, dict):
        return None

    sufficiency_raw = (
        result_payload.get("sufficiency_assessment")
        or result_payload.get("resource_evaluation")
        or result_payload.get("q3_resource_evaluation")
    )
    if not isinstance(sufficiency_raw, dict):
        return None

    resource_status = str(sufficiency_raw.get("resource_status") or "unknown")
    status_label_map = {
        "sufficient": "资源充沛",
        "degraded": "资源降级",
        "critically_lacking": "关键资源匮乏",
    }
    status_explanation_map = {
        "sufficient": "当前关键工具、执行能力与协同代理基本齐备，可以支撑正常推演与执行。",
        "degraded": "当前具备部分关键资源，但存在明显短板或瓶颈，需要保守决策与补足关键能力。",
        "critically_lacking": "当前缺少关键资源，无法安全完成核心任务，应先补足基础资产再继续执行。",
    }
    return Q3WhatDoIHaveInferenceView(
        sufficiency_assessment=Q3ResourceSufficiencyView(
            resource_status=resource_status,
            resource_status_label=str(sufficiency_raw.get("resource_status_label") or "")
            if sufficiency_raw.get("resource_status_label")
            else status_label_map.get(resource_status),
            resource_status_explanation=str(sufficiency_raw.get("resource_status_explanation") or "")
            if sufficiency_raw.get("resource_status_explanation")
            else status_explanation_map.get(resource_status),
            missing_critical_assets=_coerce_string_list(sufficiency_raw.get("missing_critical_assets")),
            bottleneck_node=sufficiency_raw.get("bottleneck_node"),
            reasoning_summary=sufficiency_raw.get("reasoning_summary"),
        )
    )



