from __future__ import annotations

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q5",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q5_what_am_i_allowed_to_do/llm_prompt.py",
        prompt_builder_name="build_q5_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_prompt.build_q5_llm_request",
        target_component="nine-question.q5.prompt",
        immutable_intent="Q5 must derive the authorized subset of Q4 actions and escalation requirements from policies and trust boundaries.",
        expected_output_key="authorization_boundary_profile",
        allowed_prompt_change_scope=[
            "tighten authorization subset constraints",
            "clarify escalation handling",
            "reduce redundant policy text",
        ],
        forbidden_prompt_changes=[
            "must not allow actions outside Q4 actionable_space",
            "must not change Q5 into generic capability analysis",
            "must not remove forbidden or escalation outputs",
        ],
        editable_prompt_sections=[
            "output_contract",
            "subset_constraints",
            "authorization_baseline",
            "q4_boundary",
            "action_source",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q5 as authorization-boundary deduction.",
                purpose="Prevent drift into generic capability analysis.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the authorization schema.",
                purpose="Allow more precise schema wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["remove escalation output"],
            ),
            build_section_policy(
                section_key="subset_constraints",
                mutable=True,
                intent="Constrain Q5 outputs to Q4 actions.",
                purpose="Allow stricter subset wording.",
                allowed_operations=["tighten subset constraints"],
                forbidden_operations=["allow invented actions"],
            ),
            build_section_policy(
                section_key="authorization_baseline",
                mutable=True,
                intent="Provide policy and trust baseline.",
                purpose="Allow more compact policy framing.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent policy state"],
            ),
            build_section_policy(
                section_key="q4_boundary",
                mutable=True,
                intent="Provide upstream capability boundary.",
                purpose="Allow better focus on relevant actions.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change q4 source meaning"],
            ),
            build_section_policy(
                section_key="action_source",
                mutable=True,
                intent="Provide verbatim action source-of-truth.",
                purpose="Allow clearer copy-only instructions.",
                allowed_operations=["clarify copy-only wording"],
                forbidden_operations=["allow paraphrase", "invent actions"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
