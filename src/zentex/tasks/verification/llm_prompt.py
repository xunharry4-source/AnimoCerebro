from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from zentex.common.prompt_template_files import render_prompt_template
from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="tasks_verification")


_MAX_TASK_REMARKS = 1500
_MAX_RESULT_OUTPUT = 3000
_MAX_CRITERIA = 12


def build_llm_evaluation_prompt(
    *,
    task_title: str,
    task_type: str,
    task_remarks: Optional[str],
    result: dict[str, Any],
    criteria: list[str],
) -> dict[str, Any]:
    criteria_text = "\n".join(
        f"- {str(item).strip()}"
        for item in criteria[:_MAX_CRITERIA]
        if str(item).strip()
    ) or "- 任务要求已满足"
    result_output = result.get("output", str(result))
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the evaluation task.",
            purpose="Keep the model focused on quality assessment instead of content generation.",
            content=_render_template("evaluation_role.md"),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="task_info",
            title="Task Info",
            intent="Provide the task requirements.",
            purpose="Ground the evaluation in task type and required outcome.",
            content=(
                f"- 标题: {_clip_text(task_title, 200)}\n"
                f"- 类型: {_clip_text(task_type, 80)}\n"
                f"- 要求: {_clip_text(task_remarks or '无详细说明', _MAX_TASK_REMARKS)}"
            ),
        ),
        build_prompt_section(
            key="submission",
            title="Submission",
            intent="Provide the submitted result.",
            purpose="Give the evaluator the concrete content to judge.",
            content=_clip_text(str(result_output), _MAX_RESULT_OUTPUT),
        ),
        build_prompt_section(
            key="criteria",
            title="Criteria",
            intent="Provide evaluation standards.",
            purpose="Constrain the judgment rubric.",
            content=criteria_text,
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required JSON response.",
            purpose="Prevent missing fields and free-form text.",
            content=_render_template("evaluation_output_contract.md"),
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain evaluation quality.",
            purpose="Keep the judgment evidence-based and compact.",
            content=_render_template("evaluation_quality_rules.md"),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": {
            "task_title": task_title,
            "task_type": task_type,
            "criteria": criteria[:_MAX_CRITERIA],
        },
    }


def _clip_text(value: Optional[str], limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return "[未提供]"
    if len(text) <= limit:
        return text
    return text[:limit] + "…（已截断）"
