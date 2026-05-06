from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q7_llm_request(
    *,
    rendered_q3_mission_boundaries: str,
    rendered_identity_kernel: str,
    rendered_q5_boundary: str,
    rendered_safety_rejections: str,
    rendered_current_intent_context: str,
    rendered_red_line_baseline: str,
    q3_mission_boundaries: dict[str, Any],
    identity_kernel: dict[str, Any],
    q5_authorization_boundary: dict[str, Any],
    safety_rejection_history: list[str],
    current_intent_context: dict[str, Any],
    red_line_baseline: dict[str, Any],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define Q7 as the red-line and constraint assessment firewall.",
            purpose="Prevent downstream objectives from bypassing identity, authorization, safety, or procedural constraints.",
            content=(
                "你是 Zentex (AnimoCerebro) 九问驱动框架的 Q7 阶段（“红线与约束”）核心风控中枢。\n"
                "你的核心职责是：基于 Q3(角色与边界)、Q5(授权黑名单) 以及底层的安全拦截记录，"
                "明确界定当前面临的绝对禁区，并输出标准的红线评估对象。\n"
                "【最高安全红线 - 禁令不可遗漏】：你输出的约束将直接决定前端的红色预警展示与下游 Q8 的任务降级转化。"
                "绝对禁止遗漏身份内核中的任何一条不可绕过约束 (non-bypassable constraints)。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="input_spec",
            title="Inputs",
            intent="Define required Q7 inputs.",
            purpose="Keep red-line assessment grounded in the exact safety sources required by the Q7 contract.",
            content=(
                "你必须基于以下输入进行客观推演与提取：\n"
                "1. [Q3_Mission_Boundaries]：Q3 阶段推演出的使命与连续性边界，特别是 continuity_boundaries 底层禁令。\n"
                "2. [Q5_Forbidden_Operations]：Q5 阶段刚刚划定的禁止操作列表（黑名单）。\n"
                "3. [Identity_Boundary]：系统底层身份边界，包含核心价值观与不可绕过约束。\n"
                "4. [Safety_Audit_Records]：安全门与审计通道近期产生的高风险拦截记录或被拒绝的操作历史。\n"
                "5. [Current_Intent_Context]：当前系统或用户试图推进的潜在方向，用于评估是否正在逼近红线。"
            ),
        ),
        build_prompt_section(
            key="q3_mission_boundaries",
            title="Q3 Mission Boundaries",
            intent="Provide Q3 continuity boundaries.",
            purpose="Force Q3 mission and continuity constraints into non_bypassable_constraints.",
            content=rendered_q3_mission_boundaries,
        ),
        build_prompt_section(
            key="identity_kernel",
            title="Identity Kernel",
            intent="Provide Identity_Kernel non-bypassable constraints.",
            purpose="Force full inheritance of identity-level constraints.",
            content=rendered_identity_kernel,
        ),
        build_prompt_section(
            key="q5_boundary",
            title="Q5 Authorization",
            intent="Provide Q5 forbidden operation blacklist.",
            purpose="Force Q5 absolute authorization limits into non_bypassable_constraints.",
            content=rendered_q5_boundary,
        ),
        build_prompt_section(
            key="safety_rejections",
            title="Safety Gate Records",
            intent="Provide recent rejected high-risk operations.",
            purpose="Populate rejected_operations_log from official safety/audit records.",
            content=rendered_safety_rejections,
        ),
        build_prompt_section(
            key="current_intent_context",
            title="Current Intent Context",
            intent="Provide current direction or user/system intent.",
            purpose="Detect active or approaching red-line hits.",
            content=rendered_current_intent_context,
        ),
        build_prompt_section(
            key="red_line_baseline",
            title="Deterministic Red-Line Baseline",
            intent="Provide deterministic preprocessed evidence assembled before the LLM call.",
            purpose="Make the LLM explain and classify evidence instead of inventing unsupported red lines.",
            content=rendered_red_line_baseline,
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define every RedLineAssessment field and its exact meaning.",
            purpose="Prevent simplified or malformed red-line assessment output.",
            content=(
                "输出契约：必须返回严格 JSON，不能包含 markdown，不能包含多余键。\n"
                "根据生产 API 契约，根节点必须强制包含 `RedLineAssessment` 对象，且只能包含该对象。\n"
                "`RedLineAssessment` 必须且只能包含 4 个字段：\n"
                "{\n"
                '  "RedLineAssessment": {\n'
                '    "current_redline_hits": ["string"],\n'
                '    "rejected_operations_log": ["string"],\n'
                '    "constraint_sources_explanation": "string",\n'
                '    "non_bypassable_constraints": ["string"]\n'
                "  }\n"
                "}\n"
                "字段规则：\n"
                "1. current_redline_hits：结合当前上下文，列出正在触碰或即将触碰的风险红线；无明显违规意图时输出空数组 []。\n"
                "2. rejected_operations_log：从 Safety_Audit_Records 提取近期被系统安全门或审计通道明确拦截的操作；无记录时输出空数组 []。\n"
                "3. constraint_sources_explanation：用一句话说明禁令来源。\n"
                "4. non_bypassable_constraints：必须将 Q3_Mission_Boundaries、Q5_Forbidden_Operations 和 Identity_Boundary 中的绝对底线去重合并，并原封不动全量输出到此处，绝不删减。\n"
                "输出前自检：如果 non_bypassable_constraints 为空，或者少于 red_line_baseline.non_bypassable_constraints，立即修正。"
            ),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q3_mission_boundaries": q3_mission_boundaries,
        "identity_kernel": identity_kernel,
        "q5_authorization_boundary": q5_authorization_boundary,
        "safety_rejection_history": safety_rejection_history[:20],
        "current_intent_context": current_intent_context,
        "red_line_baseline": red_line_baseline,
        "output_contract": {
            "RedLineAssessment": {
                "current_redline_hits": ["string"],
                "rejected_operations_log": ["string"],
                "constraint_sources_explanation": "string",
                "non_bypassable_constraints": ["string"],
            },
        },
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
