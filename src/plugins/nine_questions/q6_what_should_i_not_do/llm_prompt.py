from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q6_llm_request(
    *,
    rendered_q3_role_profile: str,
    normalized_global_constraints: list[dict[str, Any]],
    normalized_redline_hints: list[dict[str, Any]],
    forbidden_zone_baseline: dict[str, Any],
    evolution_history: list[dict[str, Any]],
    consecutive_evolution_failures: int,
    rendered_q4_boundary: str,
    rendered_q5_boundary: str,
    rendered_global_constraints: str,
    rendered_redline_hints: str,
    rendered_forbidden_baseline: str,
    rendered_evolution_history: str,
    q4_capability_boundary: Any,
    q5_authorization_boundary: Any,
    q3_role_profile: Any,
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the what-if consequence assessment task for Q6.",
            purpose="Keep the model focused on cost, consequence, reversibility, and mitigation.",
            content=(
                "你是 Zentex (AnimoCerebro) 九问驱动框架的 Q6 阶段"
                "（“What if I do it? / 代价与后果是什么”）核心认知中枢。\n"
                "你的核心职责是：基于 Q4 当前能力、Q5 禁止/授权边界、全局约束和历史失败信号，"
                "严格推演“如果我真的执行这个动作，会发生什么、代价是什么、后果是否可逆”。\n"
                "Q6 不是授权审批器，也不是红线清单所有者；Q5 已回答“我不能干什么”。"
                "Q6 只回答执行某个动作或策略后的直接后果、传导后果、代价、缓解条件和停止条件。\n"
                "你必须返回合法纯 JSON 对象。根节点只能包含 `ConsequenceAssessment` 与 "
                "`CostImpactProfile` 两个对象，禁止输出 Markdown、解释文字或任何其他顶层键。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="q3_role_profile",
            title="Q3 Role Profile",
            intent="Provide current bound execution role and main mission.",
            purpose="Ensure consequence assessment remains aligned with the current subject role and mission.",
            content=rendered_q3_role_profile,
        ),
        build_prompt_section(
            key="q4_boundary",
            title="Q4 Boundary",
            intent="Provide current verified capabilities and inferred capability boundaries.",
            purpose="Identify what action can realistically be attempted and what execution cost it creates.",
            content=rendered_q4_boundary,
        ),
        build_prompt_section(
            key="authorization_boundary",
            title="Q5 Cannot-Do Boundary",
            intent="Provide forbidden, denied, and escalation-required actions from Q5.",
            purpose="Ground the what-if analysis in actions that are prohibited, risky, or conditionally blocked.",
            content=rendered_q5_boundary,
        ),
        build_prompt_section(
            key="identity_kernel_and_q5_boundaries",
            title="Identity Kernel And Non-Bypassable Boundaries",
            intent="Provide non-bypassable constraints and protected module names.",
            purpose="Force protected safety, audit, supervision, and identity layers into consequence and stop-condition analysis.",
            content=rendered_global_constraints,
        ),
        build_prompt_section(
            key="learning_engine_signals",
            title="Learning Engine Signals",
            intent="Provide recent failure modes, blocking patterns, and consequence hints.",
            purpose="Ground consequence analysis in observed failures instead of speculation.",
            content=rendered_redline_hints,
        ),
        build_prompt_section(
            key="protected_baseline",
            title="Consequence Baseline",
            intent="Provide baseline constraints and risk signals that shape consequence severity.",
            purpose="Keep cost and stop-condition analysis aligned with durable constraint evidence.",
            content=rendered_forbidden_baseline,
        ),
        build_prompt_section(
            key="evolution_history",
            title="Outcome History",
            intent="Provide recent action or self-upgrade outcome feedback.",
            purpose="Escalate consequence severity when similar attempts failed continuously.",
            content=rendered_evolution_history,
        ),
        build_prompt_section(
            key="field_meanings",
            title="Field Meanings",
            intent="Define every required output field.",
            purpose="Prevent shallow or missing fields.",
            content=(
                "`ConsequenceAssessment.action_under_review`: 当前被评估的动作或策略；必须来自 Q4/Q5/当前上下文，不能凭空发明。\n"
                "`ConsequenceAssessment.immediate_consequences`: 如果执行该动作，最先发生的直接后果。\n"
                "`ConsequenceAssessment.downstream_consequences`: 继续传导到权限、任务、用户、系统状态或长期记忆的后果。\n"
                "`ConsequenceAssessment.consequence_severity`: 后果严重度，只能使用 low、medium、high。\n"
                "`ConsequenceAssessment.reversibility`: 后果可逆性，只能使用 reversible、partially_reversible、irreversible、unknown。\n"
                "`CostImpactProfile.operational_costs`: 时间、计算、状态、人员、上下文或流程成本。\n"
                "`CostImpactProfile.security_compliance_impacts`: 对权限、合规、审计、安全门、身份边界、租户边界造成的影响。\n"
                "`CostImpactProfile.user_trust_impacts`: 对用户信任、可解释性、可恢复性、承诺一致性的影响。\n"
                "`CostImpactProfile.mitigation_requirements`: 如果仍要推进，必须先满足的验证、审计、确认、回滚和观测条件。\n"
                "`CostImpactProfile.stop_conditions`: 哪些信号出现时必须停止执行或升级给人工处理。"
            ),
        ),
        build_prompt_section(
            key="dynamic_drift_penalty",
            title="Dynamic Drift Penalty",
            intent="Define consequence severity escalation for continuous failures.",
            purpose="Prevent repeated failed attempts from being assessed as low-cost.",
            content=(
                f"当前连续演化失败次数: {consecutive_evolution_failures}\n"
                "如果连续失败次数 >= 1，ConsequenceAssessment.consequence_severity 不得为 low。\n"
                "如果连续失败次数 >= 2，ConsequenceAssessment.consequence_severity 必须为 high，并在 mitigation_requirements 追加 mandatory_replay_regression_suite、"
                "adversarial_safety_invariance_check、human_approval_required_before_execution。\n"
                "如果连续失败次数 >= 3，必须在 stop_conditions 追加 dual_pipeline_reproducibility_gate、"
                "strict_shadow_mode_evaluation、stop_until_human_review。"
            ),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the strict consequence and cost schema.",
            purpose="Prevent empty JSON, wrong keys, or missing fields.",
            content=(
                "输出契约:\n"
                "{\n"
                '  "ConsequenceAssessment": {\n'
                '    "action_under_review": "string",\n'
                '    "immediate_consequences": ["string"],\n'
                '    "downstream_consequences": ["string"],\n'
                '    "consequence_severity": "low|medium|high",\n'
                '    "reversibility": "reversible|partially_reversible|irreversible|unknown"\n'
                "  },\n"
                '  "CostImpactProfile": {\n'
                '    "operational_costs": ["string"],\n'
                '    "security_compliance_impacts": ["string"],\n'
                '    "user_trust_impacts": ["string"],\n'
                '    "mitigation_requirements": ["string"],\n'
                '    "stop_conditions": ["string"]\n'
                "  }\n"
                "}"
            ),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q3_role_profile": q3_role_profile,
        "q4_capability_boundary": q4_capability_boundary,
        "q5_authorization_boundary": q5_authorization_boundary,
        "global_constraints": normalized_global_constraints[:16],
        "redline_hints": normalized_redline_hints[:16],
        "forbidden_zone_baseline": forbidden_zone_baseline,
        "evolution_history": evolution_history[:16],
        "consecutive_evolution_failures": consecutive_evolution_failures,
        "output_contract": {
            "ConsequenceAssessment": {
                "action_under_review": "string",
                "immediate_consequences": ["string"],
                "downstream_consequences": ["string"],
                "consequence_severity": "low|medium|high",
                "reversibility": "reversible|partially_reversible|irreversible|unknown",
            },
            "CostImpactProfile": {
                "operational_costs": ["string"],
                "security_compliance_impacts": ["string"],
                "user_trust_impacts": ["string"],
                "mitigation_requirements": ["string"],
                "stop_conditions": ["string"],
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
