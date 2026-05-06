from __future__ import annotations

from pathlib import Path

from zentex.common.prompt_upgrade_contract import (
    ModulePromptUpgradeContract,
    build_section_policy,
)


def list_prompt_upgrade_contracts() -> list[ModulePromptUpgradeContract]:
    return [
        _build_simple_decomposition_contract(),
        _build_semantic_decomposition_contract(),
        _build_semantic_analysis_contract(),
    ]


def get_prompt_upgrade_contract(prompt_id: str) -> ModulePromptUpgradeContract:
    contracts = {contract.prompt_id: contract for contract in list_prompt_upgrade_contracts()}
    return contracts[prompt_id]


def _build_simple_decomposition_contract() -> ModulePromptUpgradeContract:
    return ModulePromptUpgradeContract(
        prompt_id="tasks.core.simple_decomposition",
        module_id="tasks.core",
        prompt_file_path=str(Path(__file__).resolve().with_name("simple_llm_prompt.py")),
        prompt_builder_name="build_simple_decomposition_request",
        prompt_builder_symbol="zentex.tasks.core.simple_llm_prompt.build_simple_decomposition_request",
        target_component="tasks.core.simple_decomposition.prompt",
        immutable_intent="Simple decomposition must turn one mission into executable subtasks with a strict JSON task list.",
        expected_output_key="subtasks",
        allowed_prompt_change_scope=[
            "tighten decomposition constraints",
            "compress task input wording",
            "clarify json field contract",
        ],
        forbidden_prompt_changes=[
            "must not change decomposition into evaluation or reflection",
            "must not remove subtasks output",
            "must not allow non-json output",
        ],
        editable_prompt_sections=["task_input", "strategy_intent", "output_contract", "quality_rules"],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(section_key="role", mutable=False, intent="Preserve task decomposition identity.", purpose="Prevent drift away from subtask planning.", forbidden_operations=["change prompt identity"]),
            build_section_policy(section_key="task_input", mutable=True, intent="Provide mission data to decompose.", purpose="Allow compacting and reordering input framing.", allowed_operations=["compress evidence", "reorder emphasis"], forbidden_operations=["drop mission title", "drop mission content"]),
            build_section_policy(section_key="strategy_intent", mutable=True, intent="Explain decomposition strategy.", purpose="Allow clearer strategy-specific instructions.", allowed_operations=["tighten wording"], forbidden_operations=["change selected strategy meaning"]),
            build_section_policy(section_key="output_contract", mutable=True, intent="Enforce subtask json schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove subtasks", "change required keys"]),
            build_section_policy(section_key="quality_rules", mutable=True, intent="Constrain subtask quality.", purpose="Allow stricter execution rules.", allowed_operations=["tighten wording"], forbidden_operations=["allow free-form output"]),
        ],
        validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
    )


def _build_semantic_decomposition_contract() -> ModulePromptUpgradeContract:
    return ModulePromptUpgradeContract(
        prompt_id="tasks.core.semantic_decomposition",
        module_id="tasks.core",
        prompt_file_path=str(Path(__file__).resolve().with_name("semantic_kernel_llm_prompt.py")),
        prompt_builder_name="build_semantic_kernel_request",
        prompt_builder_symbol="zentex.tasks.core.semantic_kernel_llm_prompt.build_semantic_kernel_request",
        target_component="tasks.core.semantic_decomposition.prompt",
        immutable_intent="Semantic decomposition must combine semantic analysis with structured subtask generation.",
        expected_output_key="semantic_analysis",
        allowed_prompt_change_scope=["compress kernel config framing", "clarify semantic schema", "tighten quality rules"],
        forbidden_prompt_changes=["must not remove semantic_analysis output", "must not remove subtasks output", "must not collapse into shallow keyword matching"],
        editable_prompt_sections=["kernel_config", "task_input", "analysis_intent", "output_contract", "quality_rules"],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(section_key="role", mutable=False, intent="Preserve semantic decomposition identity.", purpose="Keep semantic reasoning plus decomposition coupled.", forbidden_operations=["change prompt identity"]),
            build_section_policy(section_key="kernel_config", mutable=True, intent="Provide kernel capability inventory.", purpose="Allow compacting capability descriptions.", allowed_operations=["compress evidence"], forbidden_operations=["invent capabilities"]),
            build_section_policy(section_key="task_input", mutable=True, intent="Provide mission and settings.", purpose="Allow compact input formatting.", allowed_operations=["compress evidence"], forbidden_operations=["drop mission content"]),
            build_section_policy(section_key="analysis_intent", mutable=True, intent="Define semantic reasoning work.", purpose="Allow clearer multi-step reasoning instructions.", allowed_operations=["tighten wording"], forbidden_operations=["remove semantic analysis step"]),
            build_section_policy(section_key="output_contract", mutable=True, intent="Enforce semantic_analysis and subtasks schema.", purpose="Allow stricter schema wording.", allowed_operations=["clarify schema"], forbidden_operations=["remove semantic_analysis", "remove subtasks"]),
            build_section_policy(section_key="quality_rules", mutable=True, intent="Constrain semantic depth.", purpose="Prevent shallow keyword decomposition.", allowed_operations=["tighten wording"], forbidden_operations=["allow shallow keyword matching"]),
        ],
        validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
    )


def _build_semantic_analysis_contract() -> ModulePromptUpgradeContract:
    return ModulePromptUpgradeContract(
        prompt_id="tasks.core.semantic_analysis",
        module_id="tasks.core",
        prompt_file_path=str(Path(__file__).resolve().with_name("semantic_kernel_llm_prompt.py")),
        prompt_builder_name="build_semantic_analysis_request",
        prompt_builder_symbol="zentex.tasks.core.semantic_kernel_llm_prompt.build_semantic_analysis_request",
        target_component="tasks.core.semantic_analysis.prompt",
        immutable_intent="Semantic analysis must produce a structured semantic profile for one mission before execution planning.",
        expected_output_key="core_objective",
        allowed_prompt_change_scope=["compress capability context", "clarify semantic profile schema"],
        forbidden_prompt_changes=["must not add task generation", "must not remove core semantic fields"],
        editable_prompt_sections=["kernel_config", "task_input", "output_contract", "quality_rules"],
        immutable_prompt_sections=["role"],
        section_change_policy=[
            build_section_policy(section_key="role", mutable=False, intent="Preserve semantic-analysis identity.", purpose="Prevent drift into planning or execution.", forbidden_operations=["change prompt identity"]),
            build_section_policy(section_key="kernel_config", mutable=True, intent="Provide analysis capability inventory.", purpose="Allow compacting model context.", allowed_operations=["compress evidence"], forbidden_operations=["invent capabilities"]),
            build_section_policy(section_key="task_input", mutable=True, intent="Provide mission to analyze.", purpose="Allow concise input framing.", allowed_operations=["compress evidence"], forbidden_operations=["drop mission content"]),
            build_section_policy(section_key="output_contract", mutable=True, intent="Enforce semantic profile schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove core fields"]),
            build_section_policy(section_key="quality_rules", mutable=True, intent="Require deep semantic analysis.", purpose="Keep analysis from becoming shallow.", allowed_operations=["tighten wording"], forbidden_operations=["allow keyword-only analysis"]),
        ],
        validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
    )
