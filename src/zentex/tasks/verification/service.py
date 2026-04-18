from __future__ import annotations

from zentex.common.prompt_upgrade_contract import ModulePromptUpgradeContract, build_section_policy


def list_prompt_upgrade_contracts() -> list[ModulePromptUpgradeContract]:
    return [
        ModulePromptUpgradeContract(
            prompt_id="tasks.verification.llm_evaluation",
            module_id="tasks.verification",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/tasks/verification/llm_prompt.py",
            prompt_builder_name="build_llm_evaluation_prompt",
            prompt_builder_symbol="zentex.tasks.verification.llm_prompt.build_llm_evaluation_prompt",
            target_component="tasks.verification.llm_evaluation.prompt",
            immutable_intent="LLM evaluation must judge task completion quality against task requirements and criteria.",
            expected_output_key="passed",
            allowed_prompt_change_scope=["compress submission context", "clarify evaluation rubric", "tighten json output schema"],
            forbidden_prompt_changes=["must not turn evaluation into decomposition", "must not remove pass/fail verdict", "must not remove evidence-based reasoning"],
            editable_prompt_sections=["task_info", "submission", "criteria", "output_contract", "quality_rules"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve evaluation identity.", purpose="Prevent drift into generation tasks.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="task_info", mutable=True, intent="Provide the task requirements.", purpose="Allow compact requirement framing.", allowed_operations=["compress evidence"], forbidden_operations=["drop task title"]),
                build_section_policy(section_key="submission", mutable=True, intent="Provide submitted result.", purpose="Allow context compression.", allowed_operations=["compress evidence"], forbidden_operations=["invent submission"]),
                build_section_policy(section_key="criteria", mutable=True, intent="Provide evaluation criteria.", purpose="Allow rubric clarification.", allowed_operations=["reorder emphasis", "tighten wording"], forbidden_operations=["change criteria meaning"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce evaluation schema.", purpose="Allow stricter schema wording.", allowed_operations=["clarify schema"], forbidden_operations=["remove verdict fields"]),
                build_section_policy(section_key="quality_rules", mutable=True, intent="Constrain evidence-based judgment.", purpose="Keep output concise and justified.", allowed_operations=["tighten wording"], forbidden_operations=["allow unsupported conclusions"]),
            ],
            validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
        )
    ]


def get_prompt_upgrade_contract(prompt_id: str) -> ModulePromptUpgradeContract:
    contracts = {contract.prompt_id: contract for contract in list_prompt_upgrade_contracts()}
    return contracts[prompt_id]
