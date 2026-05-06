from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)
from zentex.nine_questions.q8_q9_boundary import extract_goal_text


def _q9_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _q9_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _collect_prohibited_actions(*values: Any) -> list[str]:
    prohibited: list[str] = []
    key_terms = (
        "forbidden",
        "prohibited",
        "redline",
        "red_line",
        "safety",
        "constraint",
        "unauthorized",
        "禁止",
        "红线",
        "限制",
        "不可",
    )

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key)
                next_path = f"{path}.{key_text}" if path else key_text
                if any(term in key_text.lower() for term in key_terms) or any(term in key_text for term in key_terms):
                    if isinstance(item, list):
                        for entry in item:
                            text = _text(entry)
                            if text:
                                prohibited.append(text)
                    elif isinstance(item, dict):
                        text = _text(item)
                        if text and text != "{}":
                            prohibited.append(text)
                    else:
                        text = _text(item)
                        if text:
                            prohibited.append(text)
                walk(item, next_path)
        elif isinstance(value, list):
            for item in value:
                walk(item, path)

    for value in values:
        walk(value)
    if not prohibited:
        prohibited.append("Q8/Q5/Q7 未提供额外外部禁止操作；仍禁止越权、敏感数据外发、绕过安全闸门或云审计。")
    return list(dict.fromkeys(prohibited))


def _build_q8_task_intent_and_constraints(
    *,
    q8_task: Any,
    q5_authorization: dict[str, Any],
    q7_redlines: dict[str, Any],
) -> dict[str, Any]:
    task_dict = _q9_dict(q8_task)
    final_goal = extract_goal_text(task_dict) or _text(q8_task)
    return {
        "final_intervention_goal": final_goal,
        "single_q8_external_task": q8_task,
        "absolute_prohibited_actions": _collect_prohibited_actions(q8_task, q5_authorization, q7_redlines),
        "authorization_boundary": q5_authorization,
        "safety_redlines": q7_redlines,
        "decomposition_rule": "single_input_single_external_action_plan",
    }


def build_q9_external_llm_request(
    *,
    system_prompt: str,
    q8_external_tasks: list[dict[str, Any]] | list[str],
    q2_functional_plugins: list[dict[str, Any]] | list[str],
    q4_external_capabilities: dict[str, Any],
    q5_authorization: dict[str, Any] | None = None,
    q7_redlines: dict[str, Any],
    q1_environment: dict[str, Any] | None = None,
    q3_role_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    q8_task = q8_external_tasks[0] if q8_external_tasks else {}
    q5_boundary = (
        _q9_dict(q5_authorization)
        or _q9_dict(q4_external_capabilities.get("q5") if isinstance(q4_external_capabilities.get("q5"), dict) else {})
        or q4_external_capabilities
    )
    q8_task_intent_and_constraints = _build_q8_task_intent_and_constraints(
        q8_task=q8_task,
        q5_authorization=q5_boundary,
        q7_redlines=q7_redlines,
    )
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Q9 External Single Task Role",
            intent="Constrain Q9 external planning to one Q8 final intervention task per LLM call.",
            purpose="Prevent hallucinated task expansion and preserve cognitive/execution isolation.",
            content=system_prompt,
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="q8_task_intent_and_constraints",
            title="Q8 Task Intent & Constraints",
            intent="Provide exactly one external intervention final goal from Q8 plus absolute prohibited actions.",
            purpose="Force one-input one-decomposition mapping and mandatory redline inheritance.",
            content=str(q8_task_intent_and_constraints),
        ),
        build_prompt_section(
            key="q1_environment_state",
            title="Q1 Environment State",
            intent="Provide mandatory static-resource and topology evidence for Q9 external planning.",
            purpose="Force Q9 to ground external intervention in Q1 static resources, absolute paths, and topology notes.",
            content=str(q1_environment or {}),
        ),
        build_prompt_section(
            key="q2_functional_assets",
            title="Q2 External Assets",
            intent="Provide the only functional plugins, MCP tools, CLI commands, or Agents allowed in required_resources.",
            purpose="Prevent cognitive plugin execution in the external domain.",
            content=str(q2_functional_plugins),
        ),
        build_prompt_section(
            key="q3_role_identity",
            title="Q3 Role And Identity Kernel",
            intent="Provide role and identity anchors for assigned_role_profile.",
            purpose="Force Q9 to choose an explicit identity anchor for external intervention posture.",
            content=str(q3_role_identity or {}),
        ),
        build_prompt_section(
            key="q5_authorization",
            title="Q5 Authorization",
            intent="Provide authorization boundaries for the single external action.",
            purpose="Prevent actions outside the allowed boundary.",
            content=str(q5_boundary),
        ),
        build_prompt_section(
            key="q7_safety_redlines",
            title="Q7 Safety Redlines",
            intent="Provide non-bypassable operation constraints.",
            purpose="Route unsafe actions through safety gate and cloud audit, then fail closed when blocked.",
            content=str(q7_redlines),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required JSON schema.",
            purpose="Force pure JSON output with the single-task ExternalActionPlan model.",
            content=(
                "输出严格 JSON，顶层必须且只能包含 ExternalActionPlan：\n"
                "{\n"
                '  "ExternalActionPlan": {\n'
                '    "plan_objective": "string",\n'
                '    "prohibited_actions_acknowledged": ["string"],\n'
                '    "execution_target": "string",\n'
                '    "required_resources": ["string"],\n'
                '    "action_steps": [\n'
                "      {\n"
                '        "step_description": "string",\n'
                '        "step_objective": "string",\n'
                '        "verification_method": "string",\n'
                '        "involved_modules": ["string"]\n'
                "      }\n"
                "    ],\n"
                '    "success_criteria": ["string"],\n'
                '    "fallback_plan": "string",\n'
                '    "identity_anchor": "string",\n'
                '    "cognitive_certainty": "高|中|低",\n'
                '    "q_driver_refs": ["string"]\n'
                "  }\n"
                "}\n"
                "plan_objective 必须严格复述或等价继承 Q8_Task_Intent_&_Constraints.final_intervention_goal。"
                "prohibited_actions_acknowledged 必须明确列出 Q8_Task_Intent_&_Constraints.absolute_prohibited_actions。"
                "required_resources 必须从 Q2 External Assets 中选择，禁止认知插件、沙盒、反思、学习、记忆插件。"
                "action_steps 必须只拆解这一个 Q8_Task_Intent_&_Constraints，禁止新增任务或扩大范围。"
                "action_steps 每个元素必须且只能包含 step_description、step_objective、verification_method、involved_modules。"
                "action_steps 必须包含安全闸门、云审计或审批回执路径，并且每一步都不能触碰 prohibited_actions_acknowledged。"
                "success_criteria 必须描述真实外部副作用的验收标准。"
                "禁止输出内部工程代号或底层物理子任务工单。"
            ),
        ),
    ]
    model_context = {
        "Q8_Task_Intent_&_Constraints": q8_task_intent_and_constraints,
        "Q8_Tasks": q8_external_tasks,
        "Q1_Environment_State": q1_environment or {},
        "Q2_External_Assets": q2_functional_plugins,
        "Q2_Assets": q2_functional_plugins,
        "Q3_Role_IdentityKernel": q3_role_identity or {},
        "Q5_Authorization": q5_boundary,
        "Q7_Safety_Redlines": q7_redlines,
    }
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
