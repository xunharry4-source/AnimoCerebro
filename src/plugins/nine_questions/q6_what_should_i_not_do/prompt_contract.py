from __future__ import annotations

from pathlib import Path

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q6",
        prompt_file_path=str(Path(__file__).resolve().with_name("llm_prompt.py")),
        prompt_builder_name="build_q6_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q6_what_should_i_not_do.llm_prompt.build_q6_llm_request",
        target_component="nine-question.q6.prompt",
        immutable_intent="Q6 must answer What if I do it by identifying consequences, costs, reversibility, mitigation requirements, and stop conditions.",
        expected_output_key="CostImpactProfile",
        allowed_prompt_change_scope=[
            "tighten consequence assessment",
            "clarify ConsequenceAssessment/CostImpactProfile output contract",
            "reduce nonessential context noise",
            "strengthen retry-oriented validation instructions",
        ],
        forbidden_prompt_changes=[
            "must not change Q6 into authorization approval",
            "must not move Q5 cannot-do ownership back into Q6",
            "must not remove safety gate, audit channel, supervision boundary, or identity boundary impact assessment",
            "must not remove sandbox validation or read-only side-effect-free mitigation requirements",
            "must not add output top-level keys beyond ConsequenceAssessment and CostImpactProfile",
        ],
        editable_prompt_sections=[
            "q3_role_profile",
            "q4_boundary",
            "authorization_boundary",
            "identity_kernel_and_q5_boundaries",
            "learning_engine_signals",
            "protected_baseline",
            "evolution_history",
            "field_meanings",
            "dynamic_drift_penalty",
            "output_contract",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q6 as what-if consequence and cost assessment.",
                purpose="Prevent drift into authorization approval, Q5 cannot-do ownership, or unsafe self-rewrite.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="q3_role_profile",
                mutable=True,
                intent="Provide the current role and mission profile.",
                purpose="Keep Q6 consequence assessment aligned with Q3 role binding.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change upstream meaning"],
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
                section_key="authorization_boundary",
                mutable=True,
                intent="Provide authorization context.",
                purpose="Allow more compact authorization context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["change upstream meaning"],
            ),
            build_section_policy(
                section_key="identity_kernel_and_q5_boundaries",
                mutable=True,
                intent="Provide durable system constraints.",
                purpose="Allow better emphasis on non-bypassable rules.",
                allowed_operations=["tighten wording", "compress evidence"],
                forbidden_operations=["weaken constraints"],
            ),
            build_section_policy(
                section_key="learning_engine_signals",
                mutable=True,
                intent="Provide recent failure and consequence signals.",
                purpose="Allow better emphasis on observed cost and consequence evidence.",
                allowed_operations=["reorder emphasis", "compress evidence"],
                forbidden_operations=["remove key failure evidence"],
            ),
            build_section_policy(
                section_key="protected_baseline",
                mutable=True,
                intent="Provide the baseline protected-module framing.",
                purpose="Allow better baseline phrasing without changing protected boundaries.",
                allowed_operations=["tighten wording"],
                forbidden_operations=["weaken protected-module boundaries"],
            ),
            build_section_policy(
                section_key="evolution_history",
                mutable=True,
                intent="Provide recent outcome feedback.",
                purpose="Allow severity escalation after continuous failures.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["remove continuous failure signals"],
            ),
            build_section_policy(
                section_key="field_meanings",
                mutable=True,
                intent="Explain every output field.",
                purpose="Prevent shallow, missing, or ambiguous Q6 fields.",
                allowed_operations=["clarify field definitions"],
                forbidden_operations=["remove required field semantics"],
            ),
            build_section_policy(
                section_key="dynamic_drift_penalty",
                mutable=True,
                intent="Escalate consequence severity after repeated failures.",
                purpose="Prevent repeated failed attempts from being assessed as low-cost.",
                allowed_operations=["tighten convergence rules"],
                forbidden_operations=["weaken risk threshold reduction"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the ConsequenceAssessment/CostImpactProfile schema.",
                purpose="Allow stricter contract wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["add extra top-level keys", "remove mitigation_requirements", "remove stop_conditions"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
