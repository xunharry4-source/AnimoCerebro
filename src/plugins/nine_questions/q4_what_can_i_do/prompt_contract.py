from __future__ import annotations

from pathlib import Path

from zentex.common.nine_questions_prompts import (
    NineQuestionPromptUpgradeContract,
    build_section_policy,
)


def get_prompt_upgrade_contract() -> NineQuestionPromptUpgradeContract:
    return NineQuestionPromptUpgradeContract(
        question_id="q4",
        prompt_file_path=str(Path(__file__).resolve().with_name("llm_prompt.py")),
        prompt_builder_name="build_q4_llm_request",
        prompt_builder_symbol="plugins.nine_questions.q4_what_can_i_do.llm_prompt.build_q4_llm_request",
        target_component="nine-question.q4.prompt",
        immutable_intent="Q4 must derive real internal cognitive capabilities and real external physical-interference boundaries from Q2 internal assets, Q2 external assets, Q1 environment, Q3 role, and current execution domains.",
        expected_output_key="capability_boundary_profile",
        allowed_prompt_change_scope=[
            "edit Q4 prompt template files under prompt_templates/",
            "clarify baseline enforcement",
            "tighten capability boundary wording",
            "separate internal cognitive capability evidence from external physical-interference evidence",
            "compress context to actionable evidence",
        ],
        forbidden_prompt_changes=[
            "must not invent capabilities beyond available assets",
            "must not turn Q4 into permission or redline analysis",
            "must not merge Q2 internal assets and Q2 external assets into an ambiguous evidence block",
            "must not add extra output fields beyond CapabilityAssessment.inferred_capabilities",
        ],
        editable_prompt_sections=[
            "output_contract",
            "input_spec",
            "mandatory_sop",
            "q1_environment",
            "q2_internal_assets_tools",
            "q2_external_assets_tools",
            "q3_role_profile",
            "verification_probes",
            "preprocessed_evidence",
            "capability_baseline",
            "execution_domains",
        ],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(
                section_key="role",
                mutable=False,
                intent="Preserve Q4 as capability-boundary deduction.",
                purpose="Prevent conversion into permission or redline analysis.",
                forbidden_operations=["change question identity"],
            ),
            build_section_policy(
                section_key="output_contract",
                mutable=True,
                intent="Enforce the capability_boundary_profile schema.",
                purpose="Allow more precise capability schema wording.",
                allowed_operations=["clarify schema", "add explicit validation bullets"],
                forbidden_operations=["remove required schema keys", "add non-schema keys"],
            ),
            build_section_policy(
                section_key="input_spec",
                mutable=True,
                intent="Declare the file-template inputs and {{PLACEHOLDER}} substitutions.",
                purpose="Keep Q4 prompt assembly readable and auditable outside Python source edits.",
                allowed_operations=["add placeholder descriptions", "clarify input provenance"],
                forbidden_operations=["remove Q1/Q2/Q3 required inputs", "introduce undeclared placeholders"],
            ),
            build_section_policy(
                section_key="mandatory_sop",
                mutable=True,
                intent="Force separate internal and external capability reasoning.",
                purpose="Prevent Q4 from converting internal cognition into external execution capability.",
                allowed_operations=["tighten internal external separation", "clarify blocking rules"],
                forbidden_operations=["merge internal and external reasoning", "allow unsupported capabilities"],
            ),
            build_section_policy(
                section_key="q2_internal_assets_tools",
                mutable=True,
                intent="Provide Q2 internal-tools LLM output through a template file.",
                purpose="Bind internal capability claims to internal cognitive and strategy assets only.",
                allowed_operations=["clarify internal evidence usage", "compress internal evidence"],
                forbidden_operations=["use internal evidence as physical execution proof", "drop internal evidence"],
            ),
            build_section_policy(
                section_key="q2_external_assets_tools",
                mutable=True,
                intent="Provide Q2 external-tools LLM output through a template file.",
                purpose="Bind external physical-interference claims to actual external assets and permissions.",
                allowed_operations=["clarify external evidence usage", "compress external evidence"],
                forbidden_operations=["invent external assets", "drop external evidence"],
            ),
            build_section_policy(
                section_key="preprocessed_evidence",
                mutable=True,
                intent="Bind Q4 output to concrete Q3 和探针输入证据。",
                purpose="Ensure evidence context is explicit in every prompt call.",
                allowed_operations=["compress evidence", "keep evidence keys stable"],
                forbidden_operations=["drop evidence keys"],
            ),
            build_section_policy(
                section_key="capability_baseline",
                mutable=True,
                intent="Constrain capability claims to the validated baseline.",
                purpose="Allow tighter baseline enforcement wording.",
                allowed_operations=["tighten baseline wording"],
                forbidden_operations=["expand baseline scope"],
            ),
            build_section_policy(
                section_key="execution_domains",
                mutable=True,
                intent="Provide actual execution context.",
                purpose="Allow better focus on relevant execution domains.",
                allowed_operations=["compress evidence"],
                forbidden_operations=["invent domains"],
            ),
        ],
        validation_commands=[
            "PYTHONPATH=src .venv/bin/python -m py_compile src/plugins/nine_questions/q4_what_can_i_do/llm_prompt.py",
        ],
    )
