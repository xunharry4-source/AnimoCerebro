from __future__ import annotations

from typing import Any

from plugins.nine_questions.prompt_sections import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q5_llm_request(
    *,
    authorization_baseline: dict[str, Any],
    rendered_q4_boundary: str,
    actionable_space: list[str],
    snapshot_version: Any,
    q4_capability_boundary_profile: dict[str, Any],
    q4_permission_profile: Any,
    contact_policy: Any,
    tenant_scope: Any,
    agent_trust_policy: Any,
    q3_connected_agents: Any,
    functional_authorization_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the authorization-boundary task for Q5.",
            purpose="Keep the model focused on allowed actions rather than raw capabilities.",
            content="You are Zentex. Determine what actions are authorized (Q5: 我被允许做什么).",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the exact authorization schema.",
            purpose="Prevent schema drift and unauthorized action invention.",
            content=(
                "Return STRICT JSON with the top-level key: authorization_boundary_profile.\n"
                "authorization_boundary_profile MUST include:\n"
                "- allowed_action_space: list[str]\n"
                "- forbidden_action_space: list[{action:str, reason:str}]\n"
                "- contact_and_org_boundaries: object\n"
                "- requires_escalation_actions: list[str]"
            ),
        ),
        build_prompt_section(
            key="subset_constraints",
            title="Subset Constraints",
            intent="Constrain Q5 outputs to the Q4 source of truth.",
            purpose="Ensure authorization is a filtered subset of capability, not a new action set.",
            content=(
                "- allowed_action_space MUST be a strict subset of q4_capability_boundary_profile.actionable_space.\n"
                "- Every string in allowed_action_space must be copied verbatim from the Q4 actionable_space input; do not invent or paraphrase actions.\n"
                "- If an action is not present in Q4 actionable_space, it must not appear in allowed_action_space."
            ),
        ),
        build_prompt_section(
            key="authorization_baseline",
            title="Authorization Baseline",
            intent="Provide baseline policy and trust constraints.",
            purpose="Anchor authorization decisions in derived policy state.",
            content=f"Authorization baseline: {authorization_baseline}",
        ),
        build_prompt_section(
            key="q4_boundary",
            title="Q4 Boundary",
            intent="Provide current capability boundaries.",
            purpose="Ensure authorization is evaluated against actual possible actions.",
            content=rendered_q4_boundary,
        ),
        build_prompt_section(
            key="action_source",
            title="Action Source Of Truth",
            intent="Provide the raw action list for copy-only authorization.",
            purpose="Stop the model from inventing or paraphrasing actions.",
            content=f"Q4 actionable_space source of truth: {actionable_space}",
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "snapshot_version": snapshot_version,
        "q4_capability_boundary_profile": q4_capability_boundary_profile,
        "q4_permission_profile": q4_permission_profile,
        "contact_policy": contact_policy,
        "tenant_scope": tenant_scope,
        "agent_trust_policy": agent_trust_policy,
        "q3_connected_agents": q3_connected_agents,
        "authorization_baseline": authorization_baseline,
        "functional_authorization_inputs": functional_authorization_inputs[:12],
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
