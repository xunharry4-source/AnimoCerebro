from __future__ import annotations

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q9",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q9_how_should_i_act/llm_prompt.py",
        prompt_builder_name="build_q9_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q9_how_should_i_act.llm_prompt.build_q9_llm_request",
        target_component="nine-question.q9.prompt",
        immutable_intent="Q9 must choose how to act by producing evaluation, evolution, and escalation posture from Q1-Q8.",
        expected_output_key="evaluation_profile",
        allowed_prompt_change_scope=[
            "tighten posture-selection instructions",
            "clarify three-profile output contract",
            "reduce duplicated upstream summary context",
        ],
        forbidden_prompt_changes=[
            "must not change Q9 into task prioritization",
            "must not remove evaluation, evolution, or escalation outputs",
            "must not ignore Q1-Q8 synthesis",
        ],
        editable_prompt_sections=[
            "snapshot_q1_q8",
            "posture_catalog",
            "posture_baseline",
            "output_contract",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q9 as action-posture synthesis.",
                purpose="Prevent drift into task prioritization.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="snapshot_q1_q8",
                mutable=True,
                intent="Provide upstream Q1-Q8 synthesis.",
                purpose="Allow better compression of posture-relevant context.",
                allowed_operations=["compress evidence", "reorder emphasis"],
                forbidden_operations=["drop required dependencies", "invent upstream state"],
            ),
            build_section_policy(
                section_key="posture_catalog",
                mutable=True,
                intent="Provide plugin-sourced posture hints.",
                purpose="Allow more compact oracle context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent plugin outputs"],
            ),
            build_section_policy(
                section_key="posture_baseline",
                mutable=True,
                intent="Provide the posture baseline frame.",
                purpose="Allow tighter risk and escalation framing.",
                allowed_operations=["tighten wording"],
                forbidden_operations=["change posture meaning"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the three-profile Q9 output.",
                purpose="Allow stricter schema wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["remove any required profile", "change top-level keys"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/nine_questions/test_q9_prompt_contract.py -q",
        ],
    )
