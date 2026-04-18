from __future__ import annotations

from plugins.nine_questions.prompt_upgrade_contract import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q7",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q7_what_else_can_i_do/llm_prompt.py",
        prompt_builder_name="build_q7_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q7_what_else_can_i_do.llm_prompt.build_q7_llm_request",
        target_component="nine-question.q7.prompt",
        immutable_intent="Q7 must generate safe alternatives and fallback strategies that stay within Q5 authorization and Q6 red lines.",
        expected_output_key="alternative_strategy_profile",
        allowed_prompt_change_scope=[
            "tighten safe fallback generation",
            "clarify alternative strategy schema",
            "compress duplicated prior-question context",
        ],
        forbidden_prompt_changes=[
            "must not recommend actions forbidden by Q5 or Q6",
            "must not change Q7 into main-goal prioritization",
            "must not remove fallback or degradation outputs",
        ],
        editable_prompt_sections=[
            "q4_boundary",
            "q5_boundary",
            "q6_redlines",
            "resource_state",
            "functional_alternatives",
            "strategy_baseline",
            "output_contract",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q7 as fallback-strategy generation.",
                purpose="Prevent drift into primary-goal prioritization.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="q4_boundary",
                mutable=True,
                intent="Provide capability ceiling context.",
                purpose="Allow compact capability context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change upstream meaning"],
            ),
            build_section_policy(
                section_key="q5_boundary",
                mutable=True,
                intent="Provide authorization boundary context.",
                purpose="Allow compact authorization context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change upstream meaning"],
            ),
            build_section_policy(
                section_key="q6_redlines",
                mutable=True,
                intent="Provide forbidden-zone context.",
                purpose="Allow strong safety emphasis.",
                allowed_operations=["tighten wording", "compress evidence"],
                forbidden_operations=["weaken redlines"],
            ),
            build_section_policy(
                section_key="resource_state",
                mutable=True,
                intent="Provide current resource pressure context.",
                purpose="Allow more concise degradation cues.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent resource status"],
            ),
            build_section_policy(
                section_key="functional_alternatives",
                mutable=True,
                intent="Provide plugin-sourced fallback hints.",
                purpose="Allow more compact oracle evidence.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent plugin outputs"],
            ),
            build_section_policy(
                section_key="strategy_baseline",
                mutable=True,
                intent="Provide the fallback baseline frame.",
                purpose="Allow tighter schema framing.",
                allowed_operations=["tighten wording"],
                forbidden_operations=["change fallback categories"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the alternative_strategy_profile schema.",
                purpose="Allow stricter contract wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["remove fallback categories"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
