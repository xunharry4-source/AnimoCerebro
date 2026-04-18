from __future__ import annotations

from plugins.nine_questions.prompt_upgrade_contract import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q4",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q4_what_can_i_do/llm_prompt.py",
        prompt_builder_name="build_q4_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q4_what_can_i_do.llm_prompt.build_q4_llm_request",
        target_component="nine-question.q4.prompt",
        immutable_intent="Q4 must derive real actionable capability boundaries from Q3 assets, Q2 role, and current execution domains.",
        expected_output_key="capability_boundary_profile",
        allowed_prompt_change_scope=[
            "clarify baseline enforcement",
            "tighten capability boundary wording",
            "compress context to actionable evidence",
        ],
        forbidden_prompt_changes=[
            "must not invent capabilities beyond available assets",
            "must not turn Q4 into permission or redline analysis",
            "must not remove executable strategy output",
        ],
        editable_prompt_sections=[
            "output_contract",
            "capability_baseline",
            "execution_domains",
            "asset_inventory",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q4 as capability-boundary deduction.",
                purpose="Prevent conversion into permission or redline analysis.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the capability_boundary_profile schema.",
                purpose="Allow more precise capability schema wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["remove executable_strategies"],
            ),
            build_section_policy(
                section_key="capability_baseline",
                mutable=True,
                intent="Constrain capability claims to the validated baseline.",
                purpose="Allow tighter baseline enforcement wording.",
                allowed_operations=["tighten baseline wording"],
                forbidden_operations=["expand baseline scope"],
            ),
            build_section_policy(
                section_key="execution_domains",
                mutable=True,
                intent="Provide actual execution context.",
                purpose="Allow better focus on relevant execution domains.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent domains"],
            ),
            build_section_policy(
                section_key="asset_inventory",
                mutable=True,
                intent="Provide actual asset context from Q3.",
                purpose="Allow more compact asset evidence.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent assets"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
