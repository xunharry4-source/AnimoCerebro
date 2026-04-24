from __future__ import annotations

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q2",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q2_who_am_i/llm_prompt.py",
        prompt_builder_name="build_q2_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q2_who_am_i.llm_prompt.build_q2_llm_request",
        target_component="nine-question.q2.prompt",
        immutable_intent="Q2 must infer the current role, mission boundary, and duties without violating the identity kernel or Q1 scene.",
        expected_output_key="role_profile",
        allowed_prompt_change_scope=[
            "tighten role inference instructions",
            "clarify schema constraints",
            "reduce redundant context",
        ],
        forbidden_prompt_changes=[
            "must not change Q2 into capability or authorization analysis",
            "must not override immutable identity constraints",
            "must not ignore Q1 environment evidence",
        ],
        editable_prompt_sections=[
            "output_contract",
            "role_definition",
            "hard_constraints",
            "risk_preference",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q2 as role and mission inference.",
                purpose="Prevent semantic drift away from identity deduction.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the role_profile and mission_boundary schema.",
                purpose="Allow clearer schema instructions.",
                allowed_operations=["clarify schema wording"],
                forbidden_operations=["remove mission boundary", "change output meaning"],
            ),
            build_section_policy(
                section_key="role_definition",
                mutable=True,
                intent="Provide explicit role source material.",
                purpose="Allow better role-source framing.",
                allowed_operations=["compress role definitions", "highlight primary role signals"],
                forbidden_operations=["invent role definitions"],
            ),
            build_section_policy(
                section_key="hard_constraints",
                mutable=True,
                intent="Surface identity and mission hard limits.",
                purpose="Allow stricter emphasis on non-bypassable constraints.",
                allowed_operations=["tighten constraint wording"],
                forbidden_operations=["weaken hard constraints"],
            ),
            build_section_policy(
                section_key="risk_preference",
                mutable=True,
                intent="Expose current subjective risk preference.",
                purpose="Allow concise preference framing.",
                allowed_operations=["compress preference wording"],
                forbidden_operations=["remove risk signal"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
