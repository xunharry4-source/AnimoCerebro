from __future__ import annotations

from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


_MAX_TASK_REMARKS = 1500
_MAX_RESULT_OUTPUT = 3000
_MAX_CRITERIA = 12


def build_llm_evaluation_prompt(
    *,
    task_title: str,
    task_type: str,
    task_remarks: str | None,
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
            content="你是一个任务质量评估专家，需要基于任务要求和提交结果给出结构化评估。",
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
            content=(
                "返回严格 JSON，字段必须包含：\n"
                "- `passed`\n- `confidence`\n- `summary`\n- `reasoning`\n"
                "- `criteria_met`\n- `criteria_failed`"
            ),
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain evaluation quality.",
            purpose="Keep the judgment evidence-based and compact.",
            content=(
                "1. 结论必须与证据一致。\n"
                "2. `summary` 控制在 50 字内。\n"
                "3. `confidence` 必须是 0.0 到 1.0 的浮点数。\n"
                "4. 不要输出 JSON 之外的解释。"
            ),
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


def _clip_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return "[未提供]"
    if len(text) <= limit:
        return text
    return text[:limit] + "…（已截断）"
