from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q6_llm_request(
    *,
    normalized_global_constraints: list[dict[str, Any]],
    normalized_redline_hints: list[dict[str, Any]],
    forbidden_zone_baseline: dict[str, Any],
    rendered_q4_boundary: str,
    rendered_q5_boundary: str,
    rendered_global_constraints: str,
    rendered_redline_hints: str,
    rendered_forbidden_baseline: str,
    q4_capability_boundary: Any,
    q5_authorization_boundary: Any,
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the red-line extraction task for Q6.",
            purpose="Keep the model focused on what must not be done.",
            content=(
                "你现在是 G19 Preference AI 的红线与禁区生成中枢。请严格对比当前系统的『可行动作空间』与底层的『不可绕过约束/历史禁令』。\n"
                "你的任务是：明确指出在当前特定环境下，系统即使物理上能做、权限上被允许，也**绝对不该做**的事情。"
                "你必须返回严格 JSON，顶层键只能是 `forbidden_zone_profile`，禁止输出 `redline_policy_report` 或任何其他顶层键。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="q4_boundary",
            title="Q4 Boundary",
            intent="Provide what is physically executable.",
            purpose="Differentiate 'can do' from 'should not do'.",
            content=rendered_q4_boundary,
        ),
        build_prompt_section(
            key="q5_boundary",
            title="Q5 Boundary",
            intent="Provide what is formally authorized.",
            purpose="Identify red lines that remain forbidden even under authorization.",
            content=rendered_q5_boundary,
        ),
        build_prompt_section(
            key="global_constraints",
            title="Global Constraints",
            intent="Provide non-bypassable constraints.",
            purpose="Anchor forbidden zones in durable system rules.",
            content=rendered_global_constraints,
        ),
        build_prompt_section(
            key="redline_hints",
            title="Redline Hints",
            intent="Provide explicit redline clues.",
            purpose="Surface likely danger patterns and historical bans.",
            content=rendered_redline_hints,
        ),
        build_prompt_section(
            key="forbidden_baseline",
            title="Forbidden Baseline",
            intent="Provide the baseline forbidden-zone framing.",
            purpose="Keep the output aligned with prior forbidden-zone structure.",
            content=rendered_forbidden_baseline,
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the strict forbidden-zone schema.",
            purpose="Prevent empty JSON or wrong top-level keys.",
            content=(
                "输出契约:\n"
                "{\n"
                '  "forbidden_zone_profile": {\n'
                '    "absolute_red_lines": ["no fabricated runtime state"],\n'
                '    "performance_tradeoff_bans": ["no skipping audit for speed"],\n'
                '    "prohibited_strategies": ["unaudited direct production write"],\n'
                '    "contamination_risks": ["credential leakage into transcript"]\n'
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
        "global_constraints": normalized_global_constraints[:16],
        "redline_hints": normalized_redline_hints[:16],
        "forbidden_zone_baseline": forbidden_zone_baseline,
        "output_contract": {
            "forbidden_zone_profile": {
                "absolute_red_lines": ["string"],
                "performance_tradeoff_bans": ["string"],
                "prohibited_strategies": ["string"],
                "contamination_risks": ["string"],
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
