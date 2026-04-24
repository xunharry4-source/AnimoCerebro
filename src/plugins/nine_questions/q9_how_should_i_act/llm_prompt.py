from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q9_llm_request(
    *,
    system_prompt: str,
    q1_q8_summary: str,
    posture_catalog: str,
    posture_baseline: dict[str, Any],
    q1_q8: dict[str, Any],
    self_model: dict[str, Any],
    reasoning_budget: dict[str, Any],
    posture_oracles: list[str],
    functional_postures: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the action-posture task for Q9.",
            purpose="Focus the model on choosing how to act, not what task to do.",
            content=system_prompt,
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="snapshot_q1_q8",
            title="Cognitive Snapshot Q1-Q8",
            intent="Provide upstream question synthesis.",
            purpose="Ground the posture decision in prior state and current objective.",
            content=q1_q8_summary,
        ),
        build_prompt_section(
            key="posture_catalog",
            title="Posture Strategy Plugins",
            intent="Provide plugin-sourced posture hints.",
            purpose="Leverage specialized posture guidance before synthesis.",
            content=posture_catalog,
        ),
        build_prompt_section(
            key="posture_baseline",
            title="Q9 Posture Baseline",
            intent="Provide the baseline posture frame.",
            purpose="Constrain the answer to validated risk and escalation expectations.",
            content=str(posture_baseline),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required output shape.",
            purpose="Prevent drift away from the three Q9 posture profiles.",
            content=(
                "输出严格 JSON，顶层只能包含以下 3 个对象：\n"
                "- `evaluation_profile`\n"
                "- `evolution_profile`\n"
                "- `escalation_profile`\n\n"
                "`evaluation_profile` 必须包含：\n"
                "- `role_context`\n"
                "- `resource_context`\n"
                "- `risk_level`\n"
                "- `evaluation_weights`\n"
                "- `conservative_mode_triggered`\n"
                "- `evaluation_style`\n"
                "- `action_rhythm_hint`\n\n"
                "`evolution_profile` 必须包含：\n"
                "- `allowed_directions`\n"
                "- `risk_threshold`\n"
                "- `forbidden_directions`\n"
                "- `validation_requirements`\n\n"
                "`escalation_profile` 必须包含：\n"
                "- `pause_conditions`\n"
                "- `help_request_conditions`\n"
                "- `confirmation_required_conditions`\n"
                "- `revisit_conditions`\n"
                "- `rollback_conditions`\n\n"
                "禁止返回 Q8 结构或其他无关结构：\n"
                "- 不要输出 `objective_profile`\n"
                "- 不要输出 `task_queue`\n"
                "- 不要输出解释文字、markdown、代码块"
            ),
        ),
    ]
    user_prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q1_q8": q1_q8,
        "self_model": self_model,
        "reasoning_budget": reasoning_budget,
        "q9_posture_baseline": posture_baseline,
        "posture_oracles": posture_oracles[:12],
        "functional_postures": functional_postures[:12],
    }
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": user_prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
