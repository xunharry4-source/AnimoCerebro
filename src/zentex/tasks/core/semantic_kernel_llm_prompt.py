from __future__ import annotations

import json
from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


_MAX_MISSION_TITLE = 200
_MAX_MISSION_CONTENT = 4000


def build_semantic_kernel_request(
    *,
    kernel_config: dict[str, Any],
    strategy: str,
    model: str,
    context: dict[str, Any] | None,
    mission_title: str,
    mission_content: str,
) -> dict[str, Any]:
    clean_title = _clip_text(mission_title, _MAX_MISSION_TITLE)
    clean_content = _clip_text(mission_content, _MAX_MISSION_CONTENT)
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the Semantic Kernel decomposition role.",
            purpose="Keep the model focused on semantic analysis plus task planning.",
            content="你是 Semantic Kernel 任务拆解专家。",
        ),
        build_prompt_section(
            key="kernel_config",
            title="Kernel Config",
            intent="Provide the kernel capability inventory.",
            purpose="Ground the decomposition in the configured skill and plugin graph.",
            content=json.dumps(kernel_config, indent=2, ensure_ascii=False),
        ),
    ]
    prompt_sections = [
        build_prompt_section(
            key="task_input",
            title="Task Input",
            intent="Provide the mission and decomposition settings.",
            purpose="Make the model reason over the actual task, model choice, and caller context.",
            content=(
                f"- 任务标题: {clean_title}\n"
                f"- 任务内容: {clean_content}\n"
                f"- 拆分策略: {strategy}\n"
                f"- 当前模型: {model}\n"
                f"{_build_context_info(context)}"
            ),
        ),
        build_prompt_section(
            key="analysis_intent",
            title="Analysis Intent",
            intent="Explain what the semantic analysis must cover.",
            purpose="Force semantic understanding before subtask generation.",
            content=(
                "1. 理解任务核心目标与约束。\n"
                "2. 识别领域、复杂度、关键依赖和资源需求。\n"
                "3. 根据指定策略生成执行顺序与协作模式。\n"
                f"4. 策略补充要求: {_build_strategy_prompt(strategy)}"
            ),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required semantic analysis and subtask schema.",
            purpose="Prevent partial JSON and missing semantic fields.",
            content=(
                "返回严格 JSON，顶层必须包含 `semantic_analysis` 和 `subtasks`。\n"
                "`semantic_analysis` 需要包含:\n"
                "- `core_objective`\n- `domain`\n- `complexity_level`\n- `key_dependencies`\n"
                "- `resource_requirements`\n- `risk_factors`\n- `success_criteria`\n"
                "`subtasks` 中每个对象需要包含:\n"
                "- `local_id`\n- `title`\n- `task_type`\n- `content`\n- `objective`\n"
                "- `requirements`\n- `depends_on`\n- `coordination_mode`\n"
                "- `estimated_duration`\n- `priority`\n- `semantic_tags`\n"
                "- `risk_level`\n- `resource_impact`\n- `success_metrics`"
            ),
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain semantic depth and output quality.",
            purpose="Avoid shallow keyword matching and abstract subtasks.",
            content=(
                "1. 不得只做关键词匹配，必须体现语义理解。\n"
                "2. 依赖关系、风险与资源影响必须具体。\n"
                "3. 子任务必须可执行，不能只写抽象分析。\n"
                "4. 只返回 JSON，不要额外解释。"
            ),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": {
            "kernel_config": kernel_config,
            "strategy": strategy,
            "model_used": model,
            "task_context": dict(context or {}),
        },
    }


def build_semantic_analysis_request(
    *,
    kernel_config: dict[str, Any],
    model: str,
    mission_title: str,
    mission_content: str,
) -> dict[str, str]:
    clean_title = _clip_text(mission_title, _MAX_MISSION_TITLE)
    clean_content = _clip_text(mission_content, _MAX_MISSION_CONTENT)
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the semantic analysis role.",
            purpose="Focus the model on semantic understanding rather than subtask generation.",
            content="你是 Semantic Kernel 语义分析专家。",
        ),
        build_prompt_section(
            key="kernel_config",
            title="Kernel Config",
            intent="Provide the kernel capability inventory.",
            purpose="Ground the semantic analysis in the configured capability set.",
            content=f"{json.dumps(kernel_config, indent=2, ensure_ascii=False)}\n\n当前使用模型: {model}",
        ),
    ]
    prompt_sections = [
        build_prompt_section(
            key="task_input",
            title="Task Input",
            intent="Provide the task to analyze.",
            purpose="Anchor the analysis to the concrete mission title and content.",
            content=f"- 任务标题: {clean_title}\n- 任务内容: {clean_content}",
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the semantic analysis schema.",
            purpose="Ensure the model returns a complete semantic analysis object.",
            content=(
                "返回严格 JSON，字段必须包含:\n"
                "- `core_objective`\n- `domain`\n- `complexity_level`\n"
                "- `key_dependencies`\n- `resource_requirements`\n"
                "- `risk_factors`\n- `success_criteria`"
            ),
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain semantic analysis quality.",
            purpose="Avoid shallow analysis and extra free-form output.",
            content="1. 体现真实语义分析，不要只做关键词匹配。\n2. 只返回 JSON，不要输出额外解释。",
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
    }


def _build_strategy_prompt(strategy: str) -> str:
    prompts = {
        "sequential": "输出严格的顺序阶段，明确入口条件与出口标准。",
        "parallel": "识别可并行工作包，并控制协调成本与资源冲突。",
        "hybrid": "前期顺序、后期并行，平衡风险控制与执行效率。",
        "dependency_driven": "围绕关键路径和依赖强度安排执行顺序。",
    }
    return prompts.get(strategy, prompts["hybrid"])


def _build_context_info(context: dict[str, Any] | None) -> str:
    if not context:
        return "- 附加上下文: [未提供]"
    fields = [
        ("max_subtasks", "最大子任务数限制"),
        ("estimated_duration_per_subtask", "每个子任务预估时长(分钟)"),
        ("team_size", "团队规模"),
        ("complexity", "任务复杂度"),
        ("domain", "领域类型"),
        ("risk_level", "风险等级"),
    ]
    lines: list[str] = []
    for key, label in fields:
        if key in context:
            lines.append(f"- {label}: {context[key]}")
    return "\n".join(lines) if lines else "- 附加上下文: [未提供]"


def _clip_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return "[未提供]"
    if len(text) <= limit:
        return text
    return text[:limit] + "…（已截断）"
