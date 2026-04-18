from __future__ import annotations

from zentex.common.prompt_upgrade_contract import ModulePromptUpgradeContract, build_section_policy


def list_prompt_upgrade_contracts() -> list[ModulePromptUpgradeContract]:
    return [
        ModulePromptUpgradeContract(
            prompt_id="upgrade.skills.atomic_planner",
            module_id="upgrade.skills",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/upgrade/skills/atomic_planner_llm_prompt.py",
            prompt_builder_name="build_atomic_planner_prompt",
            prompt_builder_symbol="zentex.upgrade.skills.atomic_planner_llm_prompt.build_atomic_planner_prompt",
            target_component="upgrade.skills.atomic_planner.prompt",
            immutable_intent="Atomic planner must decompose one upgrade proposal into tiny executable upgrade tasks.",
            expected_output_key="tasks",
            allowed_prompt_change_scope=["compress historical patterns", "tighten atomic task schema", "clarify planning constraints"],
            forbidden_prompt_changes=["must not allow non-atomic tasks", "must not remove rollback instructions", "must not remove tasks output"],
            editable_prompt_sections=["proposal", "historical_patterns", "planning_intent", "output_contract", "hard_constraints"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve atomic planning identity.", purpose="Prevent drift into review or debugging.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="proposal", mutable=True, intent="Provide upgrade proposal facts.", purpose="Allow compact proposal framing.", allowed_operations=["compress evidence"], forbidden_operations=["invent proposal facts"]),
                build_section_policy(section_key="historical_patterns", mutable=True, intent="Provide success patterns.", purpose="Allow pattern compression.", allowed_operations=["compress evidence"], forbidden_operations=["invent patterns"]),
                build_section_policy(section_key="planning_intent", mutable=True, intent="Define atomic planning goal.", purpose="Allow clearer planning emphasis.", allowed_operations=["tighten wording"], forbidden_operations=["remove dependency ordering"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce atomic task schema.", purpose="Allow stricter schema wording.", allowed_operations=["clarify schema"], forbidden_operations=["remove tasks", "remove rollback_instructions"]),
                build_section_policy(section_key="hard_constraints", mutable=True, intent="Constrain task atomicity.", purpose="Keep tasks realistic and executable.", allowed_operations=["tighten wording"], forbidden_operations=["allow large tasks"]),
            ],
            validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
        ),
        ModulePromptUpgradeContract(
            prompt_id="upgrade.skills.auto_debugger",
            module_id="upgrade.skills",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/upgrade/skills/auto_debugger_llm_prompt.py",
            prompt_builder_name="build_root_cause_prompt",
            prompt_builder_symbol="zentex.upgrade.skills.auto_debugger_llm_prompt.build_root_cause_prompt",
            target_component="upgrade.skills.auto_debugger.prompt",
            immutable_intent="Auto debugger must identify immediate cause, root cause, trigger, and confidence from failure evidence.",
            expected_output_key="root_cause",
            allowed_prompt_change_scope=["compress failure payload", "clarify RCA schema", "tighten causal language"],
            forbidden_prompt_changes=["must not skip root cause identification", "must not remove confidence field", "must not turn RCA into remediation planning"],
            editable_prompt_sections=["failure_details", "output_contract", "quality_rules"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve RCA identity.", purpose="Prevent drift into fix generation.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="failure_details", mutable=True, intent="Provide failure evidence.", purpose="Allow compact failure framing.", allowed_operations=["compress evidence"], forbidden_operations=["invent failure evidence"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce RCA json schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove root_cause", "remove confidence"]),
                build_section_policy(section_key="quality_rules", mutable=True, intent="Constrain causal reasoning.", purpose="Keep immediate and deeper cause distinct.", allowed_operations=["tighten wording"], forbidden_operations=["merge immediate and root cause"]),
            ],
            validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
        ),
        ModulePromptUpgradeContract(
            prompt_id="upgrade.skills.auto_reviewer",
            module_id="upgrade.skills",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/upgrade/skills/auto_reviewer_llm_prompt.py",
            prompt_builder_name="build_code_review_prompt",
            prompt_builder_symbol="zentex.upgrade.skills.auto_reviewer_llm_prompt.build_code_review_prompt",
            target_component="upgrade.skills.auto_reviewer.prompt",
            immutable_intent="Auto reviewer must assess code quality risks in candidate code and return a verdict plus issue list.",
            expected_output_key="passed",
            allowed_prompt_change_scope=["compress code snippet framing", "clarify review dimensions", "tighten review schema"],
            forbidden_prompt_changes=["must not remove issues list", "must not remove pass/fail verdict", "must not turn review into code generation"],
            editable_prompt_sections=["code_snippets", "review_intent", "output_contract"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve code-review identity.", purpose="Prevent drift into implementation.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="code_snippets", mutable=True, intent="Provide candidate code under review.", purpose="Allow concise snippet framing.", allowed_operations=["compress evidence"], forbidden_operations=["invent code"]),
                build_section_policy(section_key="review_intent", mutable=True, intent="Define review dimensions.", purpose="Allow clearer quality axes.", allowed_operations=["tighten wording"], forbidden_operations=["drop security review"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce review verdict schema.", purpose="Allow stricter schema wording.", allowed_operations=["clarify schema"], forbidden_operations=["remove issues", "remove passed"]),
            ],
            validation_commands=["pytest tests/test_llm_prompt_extraction.py -q"],
        ),
    ]


def get_prompt_upgrade_contract(prompt_id: str) -> ModulePromptUpgradeContract:
    contracts = {contract.prompt_id: contract for contract in list_prompt_upgrade_contracts()}
    return contracts[prompt_id]
