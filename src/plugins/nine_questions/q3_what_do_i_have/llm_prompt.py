from __future__ import annotations

import json
from typing import Any

from plugins.nine_questions.prompt_sections import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q3_llm_request(
    *,
    cognitive_tool_registry: list[dict[str, Any]],
    execution_domain_registry: list[dict[str, Any]],
    connected_agent_catalog: list[dict[str, Any]],
    cog_tools: list[str],
    exec_domains: list[str],
    connected_agents: list[dict[str, Any]],
    activated_strategy_patches: list[str],
    accessible_workspace_zones: list[str],
    workspace_assets: dict[str, Any],
    permissions: dict[str, Any],
    tenant_permissions: list[str],
    execution_tokens: list[str],
    experience_logs: list[str],
    functional_assets: list[dict[str, Any]],
    cli_tool_registry: list[dict[str, Any]],
    mcp_server_registry: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the asset inventory task for Q3.",
            purpose="Prevent the model from drifting into planning or invention.",
            content=(
                "你现在是 Zentex 外部大脑的资产评估中枢。请严格阅读提供的资源清单及活跃插件家族。\n"
                "你的任务是完成大脑资产盘点：插件绝对禁止捏造外部资产，必须基于活跃的 Cognitive Tools、Functional Plugins、CLI Tools、MCP Servers 与 Connected Agents 进行能力声明。\n"
                "你必须输出 UnifiedAssetInventory（统一资产盘点对象），作为后续任务分发的物理基础。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Specify the exact inventory schema.",
            purpose="Prevent invalid keys and asset hallucination.",
            content=(
                "你必须返回严格 JSON，且必须满足以下结构（少字段直接失败）：\n"
                "- unified_asset_inventory: { available_cognitive_tools, available_execution_tools, connected_agents, activated_strategy_patches, accessible_workspace_zones }\n"
                "- resource_evaluation: { resource_status, missing_critical_assets, bottleneck_node, reasoning_summary }\n"
                "- 禁止输出任何额外字段，尤其禁止输出 `physical_assets`。\n"
                "- `resource_status` 只能是这三个枚举之一: `sufficient`, `degraded`, `critically_lacking`。\n"
                "- `available_execution_tools` 必须是执行域名称列表，不要输出嵌套对象。\n"
                "- `connected_agents` 必须保留为对象数组。"
            ),
        ),
        build_prompt_section(
            key="cognitive_tools",
            title="Cognitive Tools",
            intent="Provide the available cognitive tool inventory.",
            purpose="Let the model ground declarations in actual enabled cognition tools.",
            content=json.dumps(cognitive_tool_registry, ensure_ascii=False, indent=2),
        ),
        build_prompt_section(
            key="execution_tools",
            title="Execution Domains",
            intent="Provide execution-side resources.",
            purpose="Distinguish what can really be executed from what is only conceptual.",
            content=json.dumps(execution_domain_registry, ensure_ascii=False, indent=2),
        ),
        build_prompt_section(
            key="connected_agents",
            title="Connected Agents",
            intent="Provide agent-side resources.",
            purpose="Preserve connected-agent declarations as actual objects.",
            content=json.dumps(connected_agent_catalog, ensure_ascii=False, indent=2),
        ),
        build_prompt_section(
            key="output_example",
            title="Output Example",
            intent="Show the target data shape.",
            purpose="Reduce schema ambiguity when assembling the final JSON.",
            content=(
                "{\n"
                '  "unified_asset_inventory": {\n'
                f'    "available_cognitive_tools": {cog_tools},\n'
                f'    "available_execution_tools": {exec_domains},\n'
                f'    "connected_agents": {connected_agents},\n'
                f'    "activated_strategy_patches": {activated_strategy_patches},\n'
                f'    "accessible_workspace_zones": {accessible_workspace_zones}\n'
                "  },\n"
                '  "resource_evaluation": {\n'
                '    "resource_status": "degraded",\n'
                '    "missing_critical_assets": [],\n'
                '    "bottleneck_node": "execution.system",\n'
                '    "reasoning_summary": "当前具备基础认知与执行资源，但执行域仍是主要瓶颈。"\n'
                "  }\n"
                "}"
            ),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "cognitive_tool_registry": cognitive_tool_registry[:24],
        "execution_domain_registry": execution_domain_registry[:32],
        "connected_agents": connected_agent_catalog[:16],
        "activated_strategy_patches": activated_strategy_patches[:12],
        "accessible_workspace_zones": accessible_workspace_zones[:12],
        "workspace_assets": workspace_assets,
        "permissions": permissions,
        "tenant_permissions": tenant_permissions[:12],
        "execution_tokens": execution_tokens[:12],
        "experience_logs": experience_logs[:12],
        "functional_assets": functional_assets[:12],
        "cli_tool_registry": cli_tool_registry[:16],
        "mcp_server_registry": mcp_server_registry[:16],
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
