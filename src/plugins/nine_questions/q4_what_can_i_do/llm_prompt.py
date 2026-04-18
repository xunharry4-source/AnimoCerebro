from __future__ import annotations

from typing import Any

from plugins.nine_questions.prompt_sections import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q4_llm_request(
    *,
    capability_baseline: dict[str, Any],
    permission_profile: dict[str, Any],
    execution_domain_catalog: str,
    asset_inventory_summary: str,
    snapshot_version: Any,
    q1_scene_model: Any,
    q1_uncertainty_profile: Any,
    q2_role_profile: Any,
    q2_mission_boundary: Any,
    q3_unified_asset_inventory: dict[str, Any],
    q3_resource_evaluation: Any,
    q3_humanized_asset_inventory: Any,
    q3_workspaces_and_permissions: Any,
    q3_memory_and_strategy: Any,
    active_execution_domains: list[str],
    functional_capabilities: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the capability-boundary task for Q4.",
            purpose="Keep the model grounded in real capabilities rather than imagined ones.",
            content=(
                "你现在是 Zentex 外部大脑的能力评估中枢。请严格基于传入的 Q3 真实资产清单、"
                "当前的物理执行域以及环境态势，"
                "评估系统当前真正具备的行动能力。绝对禁止把不存在的能力写成可行动作。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the exact capability schema.",
            purpose="Prevent prose-heavy or schema-invalid capability outputs.",
            content=(
                "你必须返回严格 JSON，且必须满足以下结构（少字段直接失败）：\n"
                "- capability_boundary_profile: { capability_upper_limits, actionable_space, executable_strategies }\n"
                "- `capability_upper_limits` 必须是字符串数组，列出能力上限，不允许写成长段说明文本。\n"
                "- `actionable_space` 必须是字符串数组，列出当前可做动作。\n"
                "- `executable_strategies` 必须是字符串数组，列出当前可执行策略。\n"
                "- 禁止输出任何额外字段。"
            ),
        ),
        build_prompt_section(
            key="capability_baseline",
            title="Capability Baseline",
            intent="Provide the upper-bound baseline.",
            purpose="Keep the answer inside approved capability boundaries.",
            content=(
                "你必须严格落在下面给出的能力基线范围内，不允许超出能力基线虚构行动：\n"
                f"- capability_upper_limits baseline: {capability_baseline.get('capability_upper_limits')}\n"
                f"- actionable_space baseline: {capability_baseline.get('actionable_space')}\n"
                f"- executable_strategies baseline: {capability_baseline.get('executable_strategies')}\n"
                f"- permission_profile: {permission_profile}"
            ),
        ),
        build_prompt_section(
            key="execution_domains",
            title="Execution Domains",
            intent="Provide the current execution environment.",
            purpose="Link capability claims to actual execution domains.",
            content=execution_domain_catalog,
        ),
        build_prompt_section(
            key="asset_inventory",
            title="Asset Inventory Summary",
            intent="Provide the Q3 asset context.",
            purpose="Ensure capabilities are derived from owned resources.",
            content=asset_inventory_summary,
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "snapshot_version": snapshot_version,
        "q1_scene_model": q1_scene_model,
        "q1_uncertainty_profile": q1_uncertainty_profile,
        "q2_role_profile": q2_role_profile,
        "q2_mission_boundary": q2_mission_boundary,
        "q3_unified_asset_inventory": q3_unified_asset_inventory,
        "q3_resource_evaluation": q3_resource_evaluation,
        "q3_humanized_asset_inventory": q3_humanized_asset_inventory,
        "q3_workspaces_and_permissions": q3_workspaces_and_permissions,
        "q3_memory_and_strategy": q3_memory_and_strategy,
        "active_execution_domains": active_execution_domains[:24],
        "permission_profile": permission_profile,
        "capability_baseline": capability_baseline,
        "functional_capabilities": functional_capabilities[:12],
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
