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
            intent="Define the ActionPlan task for Q9.",
            purpose="Focus the model on executable action planning under verified capabilities and safety boundaries.",
            content=system_prompt,
        )
    ]
    q4_context = q1_q8.get("q4") if isinstance(q1_q8.get("q4"), dict) else {}
    boundary_context = {
        "q5": q1_q8.get("q5") if isinstance(q1_q8.get("q5"), dict) else {},
        "q7": q1_q8.get("q7") if isinstance(q1_q8.get("q7"), dict) else {},
        "self_model": self_model,
        "reasoning_budget": reasoning_budget,
        "q9_action_plan_baseline": posture_baseline,
    }
    prompt_sections = [
        build_prompt_section(
            key="objective_profile",
            title="Objective Profile From Q8",
            intent="Provide upstream Q1-Q8 synthesis with Q8 as the immediate target image.",
            purpose="Ground the action plan in Q8's objective profile while preserving Q1-Q7 evidence.",
            content=q1_q8_summary,
        ),
        build_prompt_section(
            key="verified_capabilities",
            title="Verified Capability Pool From Q4",
            intent="Provide only capabilities that have been verified by runtime evidence.",
            purpose="Prevent the plan from inventing unavailable tools, plugins, agents, or physical execution channels.",
            content=f"{posture_catalog}\n\nQ4 capability evidence: {q4_context}",
        ),
        build_prompt_section(
            key="boundaries_and_budget",
            title="Boundaries, Red Lines, And Budget",
            intent="Provide Q5/Q7 constraints plus available resource and time budget.",
            purpose="Ensure Q9 plans fail closed when action would cross authorization, safety, or budget boundaries.",
            content=str(boundary_context),
        ),
        build_prompt_section(
            key="q5_q7_authorization_redline_guard",
            title="Q5/Q7 Authorization Redline Guard",
            intent="Force Q9 ActionPlan to respect Q5/Q7 authorization limits.",
            purpose="Prevent action plans that bypass forbidden actions, collaboration limits, or safe fallback requirements.",
            content=(
                "q1_q8.q5.forbidden_action_space 与 q1_q8.q5.requires_escalation_actions 是 Q9 的授权红线。"
                "如果 q1_q8.q5.authorization_limited 为 true，或 q1_q8.q5.objective_scope 为 `single_brain_only`，"
                "则 current_action_plan 不得包含跨脑委托或高权限执行方向，risk_assessment 必须说明安全闸门风险，"
                "candidate_alternatives 必须保留人工确认、暂停、降级或回滚方案。"
            ),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required output shape.",
            purpose="Prevent drift away from the ten-field ActionPlan protocol.",
            content=(
                "输出严格 JSON，顶层必须且只能包含以下 10 个键：\n"
                "{\n"
                '  "current_action_plan": ["string"],\n'
                '  "method_selection": "string",\n'
                '  "required_resources": ["string"],\n'
                '  "assigned_role_profile": "string",\n'
                '  "risk_assessment": "string",\n'
                '  "on_failure_action": "string",\n'
                '  "estimated_confidence": 0.0,\n'
                '  "expected_results": ["string"],\n'
                '  "candidate_alternatives": ["string"],\n'
                '  "nine_question_mapping": ["string"]\n'
                "}\n\n"
                "字段要求：\n"
                "- `current_action_plan`: 为了达成 Q8 目标，需要执行的具体步骤序列；必须优先引用 Q1 静态资源、路径或拓扑依据。\n"
                "- `method_selection`: 解释为什么选择这种方法或工具链。\n"
                "- `required_resources`: 执行计划必须依赖的已验证插件、Agent、内部预算或资源。\n"
                "- `assigned_role_profile`: 指定使用哪一个身份锚点或角色子集执行任务。\n"
                "- `risk_assessment`: 评估可能触发的物理副作用、安全闸门、云审计拦截风险或内部资源占用风险。\n"
                "- `on_failure_action`: 主计划失败、被拦截或资源不足时的失败回滚与自动补偿逻辑。\n"
                "- `estimated_confidence`: 0.0-1.0 的认知确定度；低于 0.7 时必须增加预演或模拟沙盒阶段。\n"
                "- `expected_results`: 行动成功后的确切物理或认知验收条件。\n"
                "- `candidate_alternatives`: 主计划失败或被安全拦截时的降级备选方案。\n"
                "- `nine_question_mapping`: 计划引用的前置 Q1-Q8 依据映射，必须体现 Q1 静态资源数据与说明。\n\n"
                "旧字段 `expected_outcome`、`alternative_candidates`、`question_driver_refs` 禁止输出。\n\n"
                "硬性防线：\n"
                "- 动作只能使用 Q4 `verified_capabilities` 明确给出的能力。\n"
                "- 如果某一步需要 CLI/MCP/Agent/connector/external execution，必须在该步骤字符串中保留对应执行端标识，"
                "便于 Q9 后处理把内部任务与外部任务分流。\n"
                "- 对 Q8 标记为 `external_execution` 的动作，`risk_assessment` 必须说明物理副作用，"
                "`candidate_alternatives` 必须给出安全受阻时的替代方案。\n"
                "- 必须服从 Q5/Q7 的底线、红线、联系策略和不可绕过限制。\n"
                "- 不要输出 `objective_profile`、`task_queue`、`evaluation_profile`、`evolution_profile`、`escalation_profile`。\n"
                "- 不要创建、修改、删除、重排 Q8 任务。\n"
                "- 不要输出解释文字、markdown、代码块。"
            ),
        ),
    ]
    user_prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q1_q8": q1_q8,
        "self_model": self_model,
        "reasoning_budget": reasoning_budget,
        "q9_action_plan_baseline": posture_baseline,
        "posture_oracles": posture_oracles,
        "functional_postures": functional_postures,
    }
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": user_prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
