from __future__ import annotations

from typing import Any

from plugins.nine_questions.prompt_sections import (
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
            title="Task",
            intent="Define the required output shape.",
            purpose="Prevent drift away from the three Q9 posture profiles.",
            content=(
                "只有输出以下 3 个对象：\n"
                "- `evaluation_profile`\n"
                "- `evolution_profile`\n"
                "- `escalation_profile`"
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
