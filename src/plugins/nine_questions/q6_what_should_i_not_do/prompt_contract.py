from __future__ import annotations

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q6",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q6_what_should_i_not_do/llm_prompt.py",
        prompt_builder_name="build_q6_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q6_what_should_i_not_do.llm_prompt.build_q6_llm_request",
        target_component="nine-question.q6.prompt",
        immutable_intent="Q6 must identify actions that should not be taken, including absolute red lines and contamination risks, even if they seem executable.",
        expected_output_key="forbidden_zone_profile",
        allowed_prompt_change_scope=[
            "tighten redline extraction",
            "clarify forbidden-zone output contract",
            "reduce nonessential context noise",
        ],
        forbidden_prompt_changes=[
            "must not change Q6 into authorization approval",
            "must not remove absolute red lines or contamination risks",
            "must not output alternate top-level keys",
        ],
        editable_prompt_sections=[
            "q4_boundary",
            "q5_boundary",
            "global_constraints",
            "redline_hints",
            "forbidden_baseline",
            "output_contract",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q6 as forbidden-zone deduction.",
                purpose="Prevent drift into authorization approval.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="q4_boundary",
                mutable=True,
                intent="Provide executable action context.",
                purpose="Allow more compact upstream capability context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change upstream meaning"],
            ),
            build_section_policy(
                section_key="q5_boundary",
                mutable=True,
                intent="Provide authorization context.",
                purpose="Allow more compact authorization context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change upstream meaning"],
            ),
            build_section_policy(
                section_key="global_constraints",
                mutable=True,
                intent="Provide durable system constraints.",
                purpose="Allow better emphasis on non-bypassable rules.",
                allowed_operations=["tighten wording", "compress evidence"],
                forbidden_operations=["weaken constraints"],
            ),
            build_section_policy(
                section_key="redline_hints",
                mutable=True,
                intent="Provide explicit danger signals.",
                purpose="Allow better emphasis on high-risk patterns.",
                allowed_operations=["reorder emphasis", "compress evidence"],
                forbidden_operations=["remove key redlines"],
            ),
            build_section_policy(
                section_key="forbidden_baseline",
                mutable=True,
                intent="Provide the baseline forbidden-zone framing.",
                purpose="Allow better baseline phrasing without changing meaning.",
                allowed_operations=["tighten wording"],
                forbidden_operations=["change forbidden-zone meaning"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the forbidden_zone_profile schema.",
                purpose="Allow stricter contract wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["change top-level key", "remove contamination_risks"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
