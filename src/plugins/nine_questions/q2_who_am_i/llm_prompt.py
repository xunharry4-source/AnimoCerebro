from __future__ import annotations

from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q2_llm_request(
    *,
    risk_weight: float,
    role_payload_text: str,
    constraint_payload_text: str,
    workspace_domain_inference: dict[str, Any],
    q1_scene_model: dict[str, Any],
    q1_uncertainty_profile: dict[str, Any],
    identity_kernel_snapshot: dict[str, Any],
    role_payload: dict[str, Any],
    constraint_payload: dict[str, Any],
    functional_identity_inputs: list[dict[str, Any]],
    manual_role_overrides: dict[str, Any],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the identity inference task for Q2.",
            purpose="Keep the model focused on role and mission inference.",
            content=(
                "你现在是 G19 Preference AI。请根据当前所处的 environment 态势（Q1结果）和你的底层身份内核，"
                "推断出你当前最合适的任务角色、主体定位以及首要职责。"
                f"当前主观风险偏好权重: {risk_weight:.2f} (0=激进, 1=保守)。"
                "记住，你的动态角色绝不能违背底层的不可绕过约束。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Specify the required JSON structure.",
            purpose="Avoid missing role or mission boundary fields.",
            content=(
                "你必须返回严格 JSON，且必须满足以下结构（少字段直接失败）：\n"
                "- role_profile: { identity_role, active_role, task_role }\n"
                "- mission_boundary: { current_mission, priority_duties, continuity_boundaries }"
            ),
        ),
        build_prompt_section(
            key="role_definition",
            title="Role Definition",
            intent="Provide the explicit role source of truth.",
            purpose="Anchor identity inference to configured role material.",
            content=role_payload_text,
        ),
        build_prompt_section(
            key="hard_constraints",
            title="Hard Constraints",
            intent="Expose non-bypassable constraints.",
            purpose="Prevent the inferred role from violating identity kernel rules.",
            content=constraint_payload_text,
        ),
        build_prompt_section(
            key="risk_preference",
            title="Risk Preference",
            intent="Provide the active subjective preference signal.",
            purpose="Let the role posture adapt without violating hard constraints.",
            content=f"当前主观偏好: Risk={risk_weight}",
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "workspace_domain_inference": workspace_domain_inference,
        "q1_scene_model": q1_scene_model,
        "q1_uncertainty_profile": q1_uncertainty_profile,
        "identity_kernel_snapshot": identity_kernel_snapshot,
        "role_payload": role_payload,
        "constraint_payload": constraint_payload,
        "risk_weight": risk_weight,
        "functional_identity_inputs": list(functional_identity_inputs or [])[:8],
        "manual_role_overrides": manual_role_overrides,
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
