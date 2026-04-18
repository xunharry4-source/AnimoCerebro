from __future__ import annotations

from typing import Any

from plugins.nine_questions.prompt_sections import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q8_llm_request(
    *,
    system_prompt: str,
    nine_questions_summary: str,
    task_state_summary: str,
    objective_catalog: str,
    priority_baseline: dict[str, Any],
    q1_q7_snapshot: dict[str, Any],
    nine_questions: dict[str, Any],
    persistent_task_state: list[dict[str, Any]],
    active_objectives: list[str],
    functional_objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the decision-synthesis task for Q8.",
            purpose="Focus the model on current objective selection and task queue generation.",
            content=system_prompt,
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="snapshot_q1_q7",
            title="Cognitive Snapshot Q1-Q7",
            intent="Provide upstream nine-question state.",
            purpose="Ground the current objective in prior question outputs.",
            content=nine_questions_summary,
        ),
        build_prompt_section(
            key="task_state",
            title="Task State Machine",
            intent="Provide current task lifecycle state.",
            purpose="Align prioritization with ongoing, blocked, and waiting work.",
            content=task_state_summary,
        ),
        build_prompt_section(
            key="objective_catalog",
            title="Objective Strategy Plugins",
            intent="Provide plugin-sourced objective hints.",
            purpose="Leverage specialized objective proposals before synthesis.",
            content=objective_catalog,
        ),
        build_prompt_section(
            key="priority_baseline",
            title="Q8 Priority Baseline",
            intent="Provide baseline prioritization signals.",
            purpose="Constrain decisions to the validated Q8 prioritization frame.",
            content=str(priority_baseline),
        ),
        build_prompt_section(
            key="output_contract",
            title="Task",
            intent="Define the required final response shape.",
            purpose="Prevent summary-only output and enforce objective/task JSON.",
            content=(
                "综合判断，输出严格 JSON。\n"
                "顶层只能包含：\n"
                "- `objective_profile`\n"
                "- `task_queue`"
            ),
        ),
    ]
    user_prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q1_q7_snapshot": q1_q7_snapshot,
        "nine_questions": nine_questions,
        "persistent_task_state": persistent_task_state[:24],
        "q8_priority_baseline": priority_baseline,
        "active_objectives": active_objectives[:12],
        "functional_objectives": functional_objectives[:12],
    }
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": user_prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
