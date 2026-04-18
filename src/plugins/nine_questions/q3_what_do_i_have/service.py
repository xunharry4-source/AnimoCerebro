from __future__ import annotations

from plugins.nine_questions.prompt_upgrade_contract import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q3",
        prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/plugins/nine_questions/q3_what_do_i_have/llm_prompt.py",
        prompt_builder_name="build_q3_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q3_what_do_i_have.llm_prompt.build_q3_llm_request",
        target_component="nine-question.q3.prompt",
        immutable_intent="Q3 must inventory actual available assets, tools, agents, and constraints without inventing resources.",
        expected_output_key="unified_asset_inventory",
        allowed_prompt_change_scope=[
            "tighten asset inventory wording",
            "clarify allowed evidence sources",
            "reduce prompt verbosity",
        ],
        forbidden_prompt_changes=[
            "must not fabricate assets, permissions, or agents",
            "must not change Q3 into a planning or prioritization question",
            "must not remove resource sufficiency evaluation",
        ],
        editable_prompt_sections=[
            "output_contract",
            "cognitive_tools",
            "execution_tools",
            "connected_agents",
            "output_example",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q3 as asset inventory.",
                purpose="Prevent drift into planning or evaluation-only tasks.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Define the unified asset inventory schema.",
                purpose="Allow more explicit anti-hallucination wording.",
                allowed_operations=["clarify schema", "tighten anti-hallucination constraints"],
                forbidden_operations=["allow extra top-level keys"],
            ),
            build_section_policy(
                section_key="cognitive_tools",
                mutable=True,
                intent="Provide actual cognitive tool evidence.",
                purpose="Allow more compact evidence formatting.",
                allowed_operations=["compress evidence", "reorder emphasis"],
                forbidden_operations=["invent tools"],
            ),
            build_section_policy(
                section_key="execution_tools",
                mutable=True,
                intent="Provide actual execution-domain evidence.",
                purpose="Allow more compact execution evidence formatting.",
                allowed_operations=["compress evidence", "reorder emphasis"],
                forbidden_operations=["invent execution domains"],
            ),
            build_section_policy(
                section_key="connected_agents",
                mutable=True,
                intent="Provide connected agent evidence.",
                purpose="Allow compact agent evidence framing.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent agents"],
            ),
            build_section_policy(
                section_key="output_example",
                mutable=True,
                intent="Show the target output shape.",
                purpose="Allow example simplification while preserving schema meaning.",
                allowed_operations=["simplify example"],
                forbidden_operations=["change schema semantics"],
            ),
        ],
        validation_commands=[
            "pytest tests/plugins/test_nine_question_prompt_builders.py -q",
        ],
    )
