from __future__ import annotations

from pathlib import Path

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q7",
        prompt_file_path=str(Path(__file__).resolve().with_name("llm_prompt.py")),
        prompt_builder_name="build_q7_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q7_what_else_can_i_do.llm_prompt.build_q7_llm_request",
        target_component="nine-question.q7.prompt",
        immutable_intent="Q7 must assess red lines and non-bypassable constraints before Q8 objective generation.",
        expected_output_key="RedLineAssessment",
        allowed_prompt_change_scope=[
            "tighten red-line assessment",
            "clarify RedLineAssessment schema",
            "compress duplicated safety evidence context",
        ],
        forbidden_prompt_changes=[
            "must not recommend actions",
            "must not change Q7 into main-goal prioritization",
            "must not weaken non-bypassable constraints",
        ],
        editable_prompt_sections=[
            "input_spec",
            "q3_mission_boundaries",
            "identity_kernel",
            "q5_boundary",
            "safety_rejections",
            "current_intent_context",
            "red_line_baseline",
            "output_contract",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q7 as red-line and constraint assessment.",
                purpose="Prevent drift into action planning.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="q3_mission_boundaries",
                mutable=True,
                intent="Provide Q3 mission and continuity boundaries.",
                purpose="Allow compact Q3 continuity-boundary evidence.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change upstream meaning"],
            ),
            build_section_policy(
                section_key="identity_kernel",
                mutable=True,
                intent="Provide bottom identity and self-binding constraints.",
                purpose="Allow compact identity-kernel evidence.",
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
                section_key="safety_rejections",
                mutable=True,
                intent="Provide official rejected-operation history.",
                purpose="Allow strong safety emphasis.",
                allowed_operations=["tighten wording", "compress evidence"],
                forbidden_operations=["weaken redlines"],
            ),
            build_section_policy(
                section_key="current_intent_context",
                mutable=True,
                intent="Provide current system or user intent context.",
                purpose="Allow active red-line hit detection.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent current intent"],
            ),
            build_section_policy(
                section_key="red_line_baseline",
                mutable=True,
                intent="Provide deterministic red-line baseline evidence.",
                purpose="Allow tighter schema framing.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent evidence"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the RedLineAssessment schema.",
                purpose="Allow stricter contract wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["add extra output fields"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
