from __future__ import annotations

from pathlib import Path

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q9",
        prompt_file_path=str(Path(__file__).resolve().with_name("llm_prompt.py")),
        prompt_builder_name="build_q9_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q9_how_should_i_act.llm_prompt.build_q9_llm_request",
        target_component="nine-question.q9.prompt",
        immutable_intent="Q9 must choose how to act by producing a ten-field ActionPlan from Q1 static-resource evidence, Q8, Q4, and Q5/Q7 boundaries.",
        expected_output_key="current_action_plan",
        allowed_prompt_change_scope=[
            "tighten action-planning instructions",
            "clarify ten-field ActionPlan output contract",
            "reduce duplicated upstream summary context",
        ],
        forbidden_prompt_changes=[
            "must not change Q9 into task prioritization",
            "must not remove any required ActionPlan field",
            "must not ignore Q1-Q8 synthesis",
            "must not allow unverified capabilities outside Q4",
        ],
        editable_prompt_sections=[
            "objective_profile",
            "verified_capabilities",
            "boundaries_and_budget",
            "q5_q7_authorization_redline_guard",
            "output_contract",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q9 as ActionPlan synthesis.",
                purpose="Prevent drift into task prioritization or unverified execution.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="objective_profile",
                mutable=True,
                intent="Provide upstream Q1-Q8 synthesis.",
                purpose="Allow better compression of action-plan-relevant context.",
                allowed_operations=["compress evidence", "reorder emphasis"],
                forbidden_operations=["drop required dependencies", "invent upstream state"],
            ),
            build_section_policy(
                section_key="verified_capabilities",
                mutable=True,
                intent="Provide Q4 verified capability evidence.",
                purpose="Allow more compact capability context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent plugin outputs"],
            ),
            build_section_policy(
                section_key="boundaries_and_budget",
                mutable=True,
                intent="Provide safety boundaries and resource budget.",
                purpose="Allow tighter risk, fallback, and budget framing.",
                allowed_operations=["tighten wording"],
                forbidden_operations=["drop safety boundaries"],
            ),
            build_section_policy(
                section_key="q5_q7_authorization_redline_guard",
                mutable=True,
                intent="Enforce authorization and fallback red lines.",
                purpose="Prevent unsafe execution plans and missing alternatives.",
                allowed_operations=["tighten wording"],
                forbidden_operations=["weaken authorization guard"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the ten-field ActionPlan output.",
                purpose="Allow stricter schema wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["remove any required ActionPlan field", "change top-level keys"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/nine_questions/test_q9_prompt_contract.py -q",
        ],
    )
