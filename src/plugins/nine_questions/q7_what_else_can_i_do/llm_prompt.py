from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q7_llm_request(
    *,
    rendered_q4_boundary: str,
    rendered_q5_boundary: str,
    rendered_q6_redlines: str,
    rendered_q3_resource_state: str,
    rendered_functional_alternatives: str,
    rendered_strategy_baseline: str,
    q4_capability_boundary: dict[str, Any],
    q5_authorization_boundary: dict[str, Any],
    q6_forbidden_zone: dict[str, Any],
    q3_resource_evaluation: dict[str, Any],
    functional_alternatives: list[dict[str, Any]],
    alternative_strategy_baseline: dict[str, Any],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the fallback-strategy task for Q7.",
            purpose="Generate alternatives without violating prior boundaries.",
            content=(
                "你现在是 G19 Preference AI 的备选策略生成中枢。\n"
                "当前主路径已受到能力/授权/红线的约束，你的任务是：\n"
                "在不违背 Q5（授权边界）和 Q6（红线禁区）的前提下，\n"
                "生成可行的备选路径、降级策略和协作请求。\n"
                "你必须返回严格 JSON，顶层键只能是 `alternative_strategy_profile`。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="q4_boundary",
            title="Q4 Boundary",
            intent="Provide the capability ceiling.",
            purpose="Keep fallback plans executable.",
            content=rendered_q4_boundary,
        ),
        build_prompt_section(
            key="q5_boundary",
            title="Q5 Boundary",
            intent="Provide the authorization boundary.",
            purpose="Prevent unauthorized alternatives.",
            content=rendered_q5_boundary,
        ),
        build_prompt_section(
            key="q6_redlines",
            title="Q6 Redlines",
            intent="Provide the forbidden-zone boundary.",
            purpose="Prevent dangerous or contaminated alternatives.",
            content=rendered_q6_redlines,
        ),
        build_prompt_section(
            key="resource_state",
            title="Q3 Resource State",
            intent="Provide current resource pressure.",
            purpose="Encourage realistic degradation strategies.",
            content=rendered_q3_resource_state,
        ),
        build_prompt_section(
            key="functional_alternatives",
            title="Functional Alternatives",
            intent="Provide plugin-sourced alternative strategies.",
            purpose="Leverage specialized fallback hints before generating new ones.",
            content=rendered_functional_alternatives,
        ),
        build_prompt_section(
            key="strategy_baseline",
            title="Strategy Baseline",
            intent="Provide the baseline structure for alternatives.",
            purpose="Keep output aligned with expected fallback categories.",
            content=rendered_strategy_baseline,
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the exact fallback strategy schema.",
            purpose="Prevent malformed alternative strategy output.",
            content=(
                "输出契约:\n"
                "{\n"
                '  "alternative_strategy_profile": {\n'
                '    "fallback_plans": ["在当前约束内的安全替代动作"],\n'
                '    "degradation_strategies": ["降低功能范围以确保安全的策略"],\n'
                '    "collaboration_switches": ["请求人工或 Agent 协作的具体方式"],\n'
                '    "exploratory_actions": ["低风险信息收集动作"]\n'
                "  }\n"
                "}"
            ),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q4_capability_boundary": q4_capability_boundary,
        "q5_authorization_boundary": q5_authorization_boundary,
        "q6_forbidden_zone": q6_forbidden_zone,
        "q3_resource_evaluation": q3_resource_evaluation,
        "functional_alternatives": functional_alternatives[:12],
        "alternative_strategy_baseline": alternative_strategy_baseline,
        "output_contract": {
            "alternative_strategy_profile": {
                "fallback_plans": ["string"],
                "degradation_strategies": ["string"],
                "collaboration_switches": ["string"],
                "exploratory_actions": ["string"],
            }
        },
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
