from __future__ import annotations

from pathlib import Path

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q1",
        prompt_file_path=str(Path(__file__).resolve().with_name("llm_prompt.py")),
        prompt_builder_name="build_q1_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q1_where_am_i.llm_prompt.build_q1_llm_request",
        target_component="nine-question.q1.prompt",
        immutable_intent="Q1 must infer the current workspace domain and uncertainty from local evidence only.",
        expected_output_key="primary_domain",
        allowed_prompt_change_scope=[
            "tighten evidence selection",
            "clarify output schema",
            "compress noisy context",
        ],
        forbidden_prompt_changes=[
            "must not change Q1 from environment inference into task planning",
            "must not fabricate external evidence or hidden state",
            "must not remove uncertainty reporting",
        ],
        editable_prompt_sections=[
            "input_evidence",
            "output_constraint",
        ],
        immutable_prompt_sections=["system_instruction"],
        section_change_policy=[
            build_section_policy(
                section_key="system_instruction",
                mutable=False,
                intent="Preserve the question identity as workspace-domain inference.",
                purpose="Prevent the optimizer from changing Q1 into another question.",
                forbidden_operations=["rewrite question purpose", "remove strict json requirement"],
            ),
            build_section_policy(
                section_key="input_evidence",
                mutable=True,
                intent="Provide preprocessed physical host, workspace structure, and content sampling evidence.",
                purpose="Allow better compression of real local evidence without inventing context.",
                allowed_operations=["compress evidence", "reorder evidence emphasis"],
                forbidden_operations=["invent evidence", "introduce non-local evidence"],
            ),
            build_section_policy(
                section_key="output_constraint",
                mutable=True,
                intent="Define the exact Q1 WorkspaceDomainInference schema.",
                purpose="Allow stricter schema wording without changing output meaning.",
                allowed_operations=["tighten schema wording", "clarify required keys", "add explicit validation bullets"],
                forbidden_operations=["remove required keys", "add non-schema keys", "change top-level meaning"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
