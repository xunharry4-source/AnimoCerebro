from __future__ import annotations

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q8",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q8_what_should_i_do_now/llm_prompt.py",
        prompt_builder_name="build_q8_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q8_what_should_i_do_now.llm_prompt.build_q8_llm_request",
        target_component="nine-question.q8.prompt",
        immutable_intent="Q8 must decide what should be done now by synthesizing Q1-Q7 and the current task state.",
        expected_output_key="objective_profile",
        allowed_prompt_change_scope=[
            "tighten objective prioritization instructions",
            "clarify task queue schema",
            "compress large state snapshots",
        ],
        forbidden_prompt_changes=[
            "must not change Q8 into posture selection or self-reflection",
            "must not ignore Q1-Q7 dependencies",
            "must not remove task queue output",
        ],
        editable_prompt_sections=[
            "snapshot_q1_q7",
            "task_state",
            "objective_catalog",
            "priority_baseline",
            "output_contract",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q8 as current-objective and task-queue synthesis.",
                purpose="Prevent drift into posture selection or self-reflection.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="snapshot_q1_q7",
                mutable=True,
                intent="Provide upstream Q1-Q7 synthesis.",
                purpose="Allow better compression of multi-question context.",
                allowed_operations=["compress evidence", "reorder emphasis"],
                forbidden_operations=["drop required dependencies", "invent upstream state"],
            ),
            build_section_policy(
                section_key="task_state",
                mutable=True,
                intent="Provide current task lifecycle state.",
                purpose="Allow more compact task-state framing.",
                allowed_operations=["compress evidence", "highlight blockers"],
                forbidden_operations=["invent task state"],
            ),
            build_section_policy(
                section_key="objective_catalog",
                mutable=True,
                intent="Provide plugin-sourced objective hints.",
                purpose="Allow more compact oracle context.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent plugin outputs"],
            ),
            build_section_policy(
                section_key="priority_baseline",
                mutable=True,
                intent="Provide the priority baseline frame.",
                purpose="Allow clearer prioritization constraints.",
                allowed_operations=["tighten wording"],
                forbidden_operations=["change prioritization meaning"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce objective_profile and task_queue output.",
                purpose="Allow stricter final output contract wording.",
                allowed_operations=["clarify schema"],
                forbidden_operations=["remove task_queue", "change top-level keys"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/nine_questions/test_q8_authenticity_contract.py -q",
        ],
    )
