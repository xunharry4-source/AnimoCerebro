from __future__ import annotations

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q1",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q1_where_am_i/llm_prompt.py",
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
            "output_contract",
            "evidence_summary",
            "local_stats",
            "uncertainty_hints",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve the question identity as workspace-domain inference.",
                purpose="Prevent the optimizer from changing Q1 into another question.",
                forbidden_operations=["rewrite question purpose", "remove strict json requirement"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Define the exact Q1 schema.",
                purpose="Allow stricter schema wording without changing output meaning.",
                allowed_operations=["tighten schema wording", "clarify required keys"],
                forbidden_operations=["remove required keys", "change top-level meaning"],
            ),
            build_section_policy(
                section_key="evidence_summary",
                mutable=True,
                intent="Summarize the main evidence for domain inference.",
                purpose="Allow better compression of evidence context.",
                allowed_operations=["compress evidence", "reorder evidence emphasis"],
                forbidden_operations=["invent evidence", "introduce non-local evidence"],
            ),
            build_section_policy(
                section_key="local_stats",
                mutable=True,
                intent="Provide structural workspace facts.",
                purpose="Allow better highlighting of domain-relevant stats.",
                allowed_operations=["compress stats", "highlight domain cues"],
                forbidden_operations=["invent stats"],
            ),
            build_section_policy(
                section_key="uncertainty_hints",
                mutable=True,
                intent="Preserve uncertainty reporting.",
                purpose="Allow better calibration language without suppressing uncertainty.",
                allowed_operations=["clarify uncertainty wording", "compress ambiguity cues"],
                forbidden_operations=["remove uncertainty", "force certainty"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
