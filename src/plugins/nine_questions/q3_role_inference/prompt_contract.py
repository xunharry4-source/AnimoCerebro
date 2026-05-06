from __future__ import annotations

from pathlib import Path

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q3",
        prompt_file_path=str(Path(__file__).resolve().with_name("llm_prompt.py")),
        prompt_builder_name="build_q3_role_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q3_role_inference.llm_prompt.build_q3_role_llm_request",
        target_component="nine-question.q3.prompt",
        immutable_intent="Q3 must infer role profile and mission continuity from Q1/Q2 context and never treat inferred role as user override.",
        expected_output_key="role_profile",
        allowed_prompt_change_scope=[
            "tighten role inference wording",
            "clarify role source constraints",
            "clarify role alignment and continuity logic",
        ],
        forbidden_prompt_changes=[
            "must not fabricate role narratives without evidence",
            "must not change Q3 into asset inventory",
            "must not remove Q3InferenceResult / RoleProfile / MissionContinuityBoundary requirements",
        ],
        editable_prompt_sections=[
            "output_contract",
            "identity_boundary",
            "role_alignment_gate",
        ],
        immutable_prompt_sections=["system_instruction"],
        section_change_policy=[
            build_section_policy(
                section_key="system_instruction",
                mutable=False,
                intent="Preserve Q3 as role inference with explicit manual/identity constraints.",
                purpose="Prevent semantic drift into asset inventory or unrelated planning tasks.",
                forbidden_operations=["change question identity", "remove user override policy"],
            ),
            build_section_policy(
                section_key="identity_boundary",
                mutable=True,
                intent="Allow clearer identity boundary and continuity fields.",
                purpose="Improve output quality while preserving role-profile constraints.",
                allowed_operations=["clarify role_profile fields", "tighten boundary wording"],
                forbidden_operations=["remove MissionContinuityBoundary", "remove required role fields"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=False,
                intent="Define stable Q3InferenceResult schema.",
                purpose="Prevent output shape drift and unverified role claims.",
                forbidden_operations=["allow RoleProfile field drift", "allow extra top-level keys", "remove MissionContinuityBoundary"],
            ),
            build_section_policy(
                section_key="role_alignment_gate",
                mutable=True,
                intent="Expose role-alignment reasoning and continuity boundaries.",
                purpose="Support downstream reasoning with explicit alignment checks.",
                allowed_operations=["compress alignment text", "reorder continuity emphasis"],
                forbidden_operations=["remove role_alignment_gap", "remove continuity_boundaries", "drop gap explanation"],
            ),
        ],
        validation_commands=[
            "pytest tests/ci_acceptance/real_ci_modules/nine/test_q3_role_inference_clinical.py -q",
        ],
    )
