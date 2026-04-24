from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
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
    persistent_task_state: Any,
    active_objectives: list[str],
    functional_objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    if isinstance(persistent_task_state, dict):
        compact_task_state = {
            str(key): value[:6] if isinstance(value, list) else value
            for key, value in persistent_task_state.items()
        }
    elif isinstance(persistent_task_state, list):
        compact_task_state = persistent_task_state[:24]
    else:
        compact_task_state = []

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
            title="Output Contract",
            intent="Define the required final response shape.",
            purpose="Prevent summary-only output and enforce objective/task JSON.",
            content=(
                "综合判断，输出严格 JSON。\n"
                "顶层只能包含：\n"
                "- `objective_profile`\n"
                "- `task_queue`\n\n"
                "`objective_profile` 必须包含以下字段：\n"
                "- `current_mission`\n"
                "- `primary_objectives`\n"
                "- `secondary_objectives`\n"
                "- `completion_conditions`\n"
                "- `pause_conditions`\n"
                "- `escalation_conditions`\n"
                "- `current_phase_tasks`\n"
                "- `priority_order`\n\n"
                "`task_queue` 必须是对象，且只能包含：\n"
                "- `next_self_tasks`\n"
                "- `blocked_self_tasks`\n"
                "- `proactive_actions`\n\n"
                "禁止返回旧字段或旧结构：\n"
                "- 不要使用 `main_objective`\n"
                "- 不要使用 `rationale`\n"
                "- 不要使用 `constraints_adherence`\n"
                "- 不要使用 `derived_capabilities`\n"
                "- 不要把 `task_queue` 输出成数组\n"
                "- 不要输出任何解释文字、markdown、代码块"
            ),
        ),
    ]
    user_prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q1_q7_snapshot": q1_q7_snapshot,
        "nine_questions": nine_questions,
        "persistent_task_state": compact_task_state,
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
