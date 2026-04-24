from __future__ import annotations

from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


_MAX_MISSION_TITLE = 200
_MAX_MISSION_CONTENT = 3000


def build_simple_decomposition_request(
    *,
    strategy: str,
    mission_title: str,
    mission_content: str,
    context: dict[str, Optional[Any]],
) -> dict[str, Any]:
    strategy_prompt = _build_strategy_prompt(strategy)
    context_info = _build_context_info(context)
    clean_title = _clip_text(mission_title, _MAX_MISSION_TITLE)
    clean_content = _clip_text(mission_content, _MAX_MISSION_CONTENT)
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the decomposition responsibility.",
            purpose="Keep the model focused on executable subtask planning.",
            content="你是一个专业的任务管理专家，擅长将复杂任务拆解为可执行的子任务。",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="task_input",
            title="Task Input",
            intent="Provide the mission to decompose.",
            purpose="Ground the decomposition in the actual task title, content, and strategy.",
            content=(
                f"- 任务标题: {clean_title}\n"
                f"- 任务内容: {clean_content}\n"
                f"- 拆分策略: {strategy}\n"
                f"{context_info}"
            ),
        ),
        build_prompt_section(
            key="strategy_intent",
            title="Strategy Intent",
            intent="Explain the selected decomposition strategy.",
            purpose="Guide the model toward the expected ordering pattern.",
            content=strategy_prompt,
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required JSON output structure.",
            purpose="Prevent free-form output and missing fields.",
            content=(
                "返回严格 JSON，顶层必须包含 `subtasks` 数组。\n"
                "每个子任务必须包含:\n"
                "- `local_id`\n- `title`\n- `task_type`\n- `content`\n- `objective`\n"
                "- `requirements`\n- `depends_on`\n- `coordination_mode`\n"
                "- `estimated_duration`\n- `priority`"
            ),
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain the quality of generated subtasks.",
            purpose="Ensure decomposed tasks remain executable and internally consistent.",
            content=(
                "1. 每个子任务必须是可执行动作，不得空泛。\n"
                "2. `task_type` 固定为 `cognitive_step`。\n"
                "3. 依赖关系必须合理，不得循环依赖。\n"
                "4. `estimated_duration` 必须在 30-240 分钟之间。\n"
                "5. `priority` 只能是 `high`、`medium`、`low`。\n"
                "6. `coordination_mode` 必须与执行方式匹配。\n"
                "7. 只返回 JSON，不要输出额外解释。"
            ),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": {"strategy": strategy, "task_context": dict(context or {})},
    }


def _build_strategy_prompt(strategy: str) -> str:
    prompts = {
        "sequential": (
            "按严格顺序拆分任务，每个阶段依赖前一个阶段，"
            "优先采用 分析 -> 规划 -> 准备 -> 执行 -> 验证 -> 收尾 的流程。"
        ),
        "parallel": "识别可以并行执行的工作，减少总耗时，同时控制协调成本。",
        "hybrid": "前期以顺序拆分保证分析充分，后期识别可并行阶段加速执行。",
        "dependency_driven": "围绕依赖关系拆分任务，先识别关键路径，再安排执行顺序。",
    }
    return prompts.get(strategy, prompts["hybrid"])


def _build_context_info(context: dict[str, Optional[Any]]) -> str:
    if not context:
        return "- 附加约束: [未提供]"
    lines: list[str] = []
    if "max_subtasks" in context:
        lines.append(f"- 最大子任务数: {context['max_subtasks']}")
    if "estimated_duration_per_subtask" in context:
        lines.append(f"- 每个子任务预估时长: {context['estimated_duration_per_subtask']}分钟")
    return "\n".join(lines) if lines else "- 附加约束: [未提供]"


def _clip_text(value: Optional[str], limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return "[未提供]"
    if len(text) <= limit:
        return text
    return text[:limit] + "…（已截断）"
