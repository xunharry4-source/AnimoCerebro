from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)
from zentex.nine_questions.q8_q9_boundary import extract_goal_text


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mandatory_q_driver_refs(
    *,
    q1_environment: dict[str, Any] | None,
    q8_internal_intents: list[dict[str, Any]] | list[str],
) -> list[str]:
    q1 = q1_environment if isinstance(q1_environment, dict) else {}
    q8_goal = q8_internal_intents[0] if q8_internal_intents else {}
    return [
        (
            "Q1 静态资源依据："
            f"静态资源={q1.get('internal_static_resources') or q1.get('static_resources') or []}; "
            f"资源数据分布={_text(q1.get('static_resource_distribution') or q1.get('workspace_topology')) or '未说明'}; "
            f"盲区={q1.get('uncertainty_blind_spots') or []}"
        ),
        f"Q8 单一任务意图与约束：{q8_goal}",
    ]


def build_q9_internal_llm_request(
    *,
    system_prompt: str,
    q8_internal_intents: list[dict[str, Any]] | list[str],
    q2_cognitive_capabilities_abstract: list[dict[str, Any]] | list[str],
    brain_organ_states: dict[str, Any],
    q1_environment: dict[str, Any] | None = None,
    q3_role_identity: dict[str, Any] | None = None,
    q4_capabilities_q7_redlines: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mandatory_q_driver_refs = _mandatory_q_driver_refs(
        q1_environment=q1_environment,
        q8_internal_intents=q8_internal_intents,
    )
    q8_final_goal = extract_goal_text(q8_internal_intents[0] if q8_internal_intents else "")
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Constrain Q9 internal planning to cognitive-only governance.",
            purpose="Prevent external side effects while producing one InternalActionPlan for one Q8 task.",
            content=system_prompt,
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="q1_environment",
            title="Q1 Environment",
            intent="Provide the mandatory static-resource evidence for Q9 internal planning.",
            purpose="Force Q9 to ground the plan in Q1 static resources, distribution notes, and uncertainty blind spots.",
            content=str(q1_environment or {}),
        ),
        build_prompt_section(
            key="q8_internal_intents",
            title="Q8 Task Intent And Constraints",
            intent="Provide the only single Q8 task intent Q9 internal planning may refine.",
            purpose="Block task hallucination and keep Q9 scoped to exactly one Q8 internal task.",
            content=str({"q8_final_goal": q8_final_goal, "q8_internal_intents": q8_internal_intents}),
        ),
        build_prompt_section(
            key="mandatory_q_driver_refs",
            title="Mandatory Q Driver Refs",
            intent="Provide exact Q1/Q8 evidence strings that must be copied into InternalActionPlan.q_driver_refs.",
            purpose="Prevent structurally valid JSON that fails Q9 business evidence validation.",
            content=str(mandatory_q_driver_refs),
        ),
        build_prompt_section(
            key="q2_assets",
            title="Q2 Assets",
            intent="Provide cognitive plugins and brain organs that Q9 may designate as requested executors.",
            purpose="Force executor designations to be copied from Q2 instead of invented.",
            content=str(q2_cognitive_capabilities_abstract),
        ),
        build_prompt_section(
            key="brain_organ_states",
            title="Q3 Role And Identity Kernel",
            intent="Provide role and identity anchors for assigned_role_profile.",
            purpose="Force Q9 to choose an explicit identity anchor for execution posture.",
            content=str(q3_role_identity or {}),
        ),
        build_prompt_section(
            key="q4_q7_boundaries",
            title="Q4 Capabilities And Q7 Redlines",
            intent="Provide internal capability limits and hard red lines.",
            purpose="Ground risk assessment and fallback planning in allowed internal boundaries.",
            content=str(q4_capabilities_q7_redlines or {}),
        ),
        build_prompt_section(
            key="brain_organ_states",
            title="Brain Organ States",
            intent="Provide internal brain-engine load and health state.",
            purpose="Ground risk assessment and fallback planning in internal runtime state.",
            content=str(brain_organ_states),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required JSON schema.",
            purpose="Force pure JSON output with the InternalActionPlan model.",
            content=(
                "输出严格 JSON，顶层必须且只能包含 InternalActionPlan：\n"
                "{\n"
                '  "InternalActionPlan": {\n'
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
                '    "cognitive_certainty": "string",\n'
                '    "q_driver_refs": ["string"]\n'
                "  }\n"
                "}\n"
                "plan_objective 必须严格复述 Q8 Task Intent And Constraints.q8_final_goal。"
                "输入上下文键 Q8_Tasks 与 Q2_Assets 是本次内部蓝图的唯一任务锚点和资源锚点。"
                "action_steps 每个对象必须且只能包含 step_description、step_objective、verification_method、involved_modules。"
                "action_steps 数组内禁止出现 success_criteria、fallback_plan、identity_anchor、cognitive_certainty、q_driver_refs。"
                "success_criteria、fallback_plan、identity_anchor、cognitive_certainty、q_driver_refs 必须是 InternalActionPlan 的直接字段，不得嵌套在 action_steps 中。"
                "required_resources、execution_target、involved_modules 必须保持纯内部认知域。"
                "q_driver_refs 必须体现 Q1 内部静态资源数据、Q8 单一目标与 Q8 禁令。"
                "q_driver_refs 必须逐字包含 Mandatory Q Driver Refs 中的每一个字符串。"
                "合法输出示例："
                '{"InternalActionPlan":{"plan_objective":"复述单一 Q8 内部目标",'
                '"prohibited_actions_acknowledged":["禁止外部副作用"],'
                '"execution_target":"MemoryEngine",'
                '"required_resources":["semantic_clustering"],'
                '"action_steps":[{"step_description":"读取内部证据摘要",'
                '"step_objective":"形成内部分析基线",'
                '"verification_method":"确认内部摘要包含 Q1 与 Q8 依据",'
                '"involved_modules":["MemoryEngine"]}],'
                '"success_criteria":["生成可查询的内部认知蓝图"],'
                '"fallback_plan":"若内部证据不足则终止并请求补充上下文",'
                '"identity_anchor":"严谨诊断员",'
                '"cognitive_certainty":"中",'
                '"q_driver_refs":["Q1 静态资源依据：静态资源=[]; 资源数据分布=未说明; 盲区=[]",'
                '"Q8 单一任务意图与约束：示例"]}}'
                "禁止输出 markdown、解释文字、Functional Plugin、外部文件修改、脚本执行、网络请求、CLI、MCP、Agent、connector。"
            ),
        ),
    ]
    model_context = {
        "Q1_Environment": q1_environment or {},
        "Q8_Tasks": q8_internal_intents,
        "Q8_Final_Goal": q8_final_goal,
        "Q2_Assets": q2_cognitive_capabilities_abstract,
        "Q3_Role_IdentityKernel": q3_role_identity or {},
        "Q4_Capabilities_Q7_Redlines": q4_capabilities_q7_redlines or {},
        "Mandatory_Q_Driver_Refs": mandatory_q_driver_refs,
        "Brain_Organ_States": brain_organ_states,
    }
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
