from __future__ import annotations

from zentex.common.prompt_upgrade_contract import ModulePromptUpgradeContract, build_section_policy


def list_prompt_upgrade_contracts() -> list[ModulePromptUpgradeContract]:
    return [
        ModulePromptUpgradeContract(
            prompt_id="memory.consolidation.summary",
            module_id="memory.consolidation",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/memory/consolidation/llm_prompt.py",
            prompt_builder_name="build_consolidation_summary_prompt",
            prompt_builder_symbol="zentex.memory.consolidation.llm_prompt.build_consolidation_summary_prompt",
            target_component="memory.consolidation.summary.prompt",
            immutable_intent="Consolidation prompt must summarize reusable memory value and return promotion and compression decisions.",
            expected_output_key="summary",
            allowed_prompt_change_scope=["tighten summary guidance", "clarify consolidation output schema"],
            forbidden_prompt_changes=["must not remove promotion_candidates", "must not remove compressed_refs", "must not turn consolidation into online planning"],
            editable_prompt_sections=["output_contract", "quality_rules"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve consolidation summarization identity.", purpose="Prevent drift into planning or chat response.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce consolidation schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove promotion_candidates", "remove compressed_refs"]),
                build_section_policy(section_key="quality_rules", mutable=True, intent="Constrain reusable-memory judgment.", purpose="Keep focus on durable value and compression.", allowed_operations=["tighten wording"], forbidden_operations=["allow transcript-style repetition"]),
            ],
            validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
        )
    ]


def get_prompt_upgrade_contract(prompt_id: str) -> ModulePromptUpgradeContract:
    contracts = {contract.prompt_id: contract for contract in list_prompt_upgrade_contracts()}
    return contracts[prompt_id]
