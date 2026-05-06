from __future__ import annotations

from pathlib import Path

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q5",
        prompt_file_path=str(Path(__file__).resolve().with_name("llm_prompt.py")),
        prompt_builder_name="build_q5_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_prompt.build_q5_llm_request",
        target_component="nine-question.q5.prompt",
        immutable_intent="Q5 must derive the authorized subset of Q4 actions and escalation requirements from policies and trust boundaries.",
        expected_output_key="authorization_boundary",
        allowed_prompt_change_scope=[
            "tighten AuthorizationBoundary subset constraints",
            "clarify contact policy and organization boundary handling",
            "clarify identity-kernel evidence wording",
            "enforce the AuthorizationBoundary root-object JSON contract",
        ],
        forbidden_prompt_changes=[
            "must not allow operations outside Q4 actionable_space",
            "must not change Q5 into generic capability analysis",
            "must not remove forbidden operation outputs",
            "must not return legacy authorization_boundary_profile as the LLM output contract",
        ],
        editable_prompt_sections=[
            "user_context",
            "authorization_guard",
            "output_constraint",
        ],
        immutable_prompt_sections=[],
        section_change_policy=[
            build_section_policy(
                section_key="system_instruction",
                mutable=True,
                intent="Preserve Q5 as authorization-boundary deduction.",
                purpose="Allow strict Q5 AuthorizationBoundary schema updates without drifting into generic capability analysis.",
                allowed_operations=["tighten root AuthorizationBoundary schema", "clarify least-privilege rules"],
                forbidden_operations=["change question identity", "allow operations outside Q4 actionable_space"],
            ),
            build_section_policy(
                section_key="user_context",
                mutable=True,
                intent="Provide identity, host permission, and collaboration evidence.",
                purpose="Allow compact evidence formatting without changing source truth.",
                allowed_operations=["compress evidence", "reorder emphasis"],
                forbidden_operations=["invent policy state", "invent identity constraints"],
            ),
            build_section_policy(
                section_key="authorization_guard",
                mutable=True,
                intent="Constrain Q5 outputs to Q4 operations.",
                purpose="Allow stricter subset wording.",
                allowed_operations=["tighten subset constraints"],
                forbidden_operations=["allow invented operations"],
            ),
            build_section_policy(
                section_key="output_constraint",
                mutable=True,
                intent="Define strict AuthorizationBoundary schema.",
                purpose="Allow clearer schema wording while preserving the root AuthorizationBoundary object.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["allow extra top-level keys", "restore legacy flat output"],
            ),
        ],
        validation_commands=[
            "pytest tests/ci_acceptance/real_ci_modules/nine/test_q5_clinical.py -q",
        ],
    )
