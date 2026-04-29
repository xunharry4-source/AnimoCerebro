from __future__ import annotations

"""
DSPy-backed LLM upgrade planner.

This service is the core entrypoint for LLM optimization upgrades. It does not
pretend to optimize models when DSPy is missing; instead it validates the
request, checks runtime readiness, and returns a candidate plan that can later
be executed by a real optimization worker.
"""

from zentex.upgrade.llm.models import LLMUpgradeCandidate, LLMUpgradeRequest
from zentex.upgrade.base_models import SelfUpgradeProposal
from typing import Any
from zentex.common.prompt_upgrade_contract import ModulePromptUpgradeContract, build_section_policy
from zentex.upgrade.llm.planner import (
    LLMEvolutionTargetPlanner,
    LLMUpgradePlanner,
    OptimizationNeedsDetector,
)


class DSPyLLMUpgradeService:
    """Fail-closed planner for DSPy-driven LLM optimization candidates."""

    def __init__(self, *, planner: LLMUpgradePlanner | None = None) -> None:
        self._planner = planner or LLMUpgradePlanner()

    def assert_runtime_ready(self) -> None:
        self._planner.assert_runtime_ready()

    def plan_candidate(self, request: LLMUpgradeRequest) -> LLMUpgradeCandidate:
        return self._planner.plan_candidate(request)

    def generate_dspy_primitives(self, objective_summary: str, target_metric: str) -> dict[str, str]:
        return self._planner.generate_primitives(
            objective_summary=objective_summary,
            target_metric=target_metric,
        )

    def detect_optimization_needs(self, failure_logs: list[dict[str, Any]]) -> list[SelfUpgradeProposal]:
        return OptimizationNeedsDetector().detect(failure_logs)


class LLMEvolutionPlanner:
    """Automatic target metric and capability identification via LLM reasoning."""

    def identify_optimal_targets(self, failure_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return LLMEvolutionTargetPlanner().identify_optimal_targets(failure_history)


class LLMUpgradeValidator:
    """Offline evaluation and regression testing framework (Function 59 gap)."""

    def run_offline_evaluation(self, candidate: LLMUpgradeCandidate, dataset: list[dict[str, Any]]) -> dict[str, Any]:
        """Run programmatic evaluation of a candidate LLM program."""
        raise RuntimeError(
            "LLM upgrade evaluation requires a real evaluator runner and persisted artifact refs; "
            "simulated metrics are not allowed."
        )


def list_prompt_upgrade_contracts() -> list[ModulePromptUpgradeContract]:
    return [
        ModulePromptUpgradeContract(
            prompt_id="upgrade.llm.dspy_primitive_generation",
            module_id="upgrade.llm",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/upgrade/llm/prompt_builders.py",
            prompt_builder_name="build_dspy_primitive_generation_request",
            prompt_builder_symbol="zentex.upgrade.llm.prompt_builders.build_dspy_primitive_generation_request",
            target_component="upgrade.llm.dspy_primitive_generation.prompt",
            immutable_intent="DSPy primitive generation must return signature, module, and metric code for one optimization objective.",
            expected_output_key="signature",
            allowed_prompt_change_scope=["tighten code-generation schema", "compress objective framing"],
            forbidden_prompt_changes=["must not remove signature", "must not remove module", "must not remove metric"],
            editable_prompt_sections=["objective", "target_metric", "output_contract"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve dspy primitive generation identity.", purpose="Prevent drift away from code primitive generation.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="objective", mutable=True, intent="Provide optimization objective.", purpose="Allow compact objective framing.", allowed_operations=["compress evidence"], forbidden_operations=["change objective meaning"]),
                build_section_policy(section_key="target_metric", mutable=True, intent="Provide optimization metric.", purpose="Allow compact metric framing.", allowed_operations=["tighten wording"], forbidden_operations=["change target metric"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce primitive code schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove signature", "remove module", "remove metric"]),
            ],
            validation_commands=["pytest tests/test_module_prompt_upgrade_contracts.py -q"],
        ),
        ModulePromptUpgradeContract(
            prompt_id="upgrade.llm.optimization_needs",
            module_id="upgrade.llm",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/upgrade/llm/prompt_builders.py",
            prompt_builder_name="build_optimization_needs_request",
            prompt_builder_symbol="zentex.upgrade.llm.prompt_builders.build_optimization_needs_request",
            target_component="upgrade.llm.optimization_needs.prompt",
            immutable_intent="Optimization-needs analysis must identify high-value LLM optimization opportunities from failure logs.",
            expected_output_key="candidate_directions",
            allowed_prompt_change_scope=["clarify failure-pattern analysis task", "tighten output wording"],
            forbidden_prompt_changes=["must not remove optimization direction output", "must not invent failures not present in logs"],
            editable_prompt_sections=["analysis_task", "output_contract"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve optimization-needs analysis identity.", purpose="Prevent drift into code generation.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="analysis_task", mutable=True, intent="Define failure-pattern analysis task.", purpose="Allow clearer optimization reasoning instructions.", allowed_operations=["tighten wording"], forbidden_operations=["change task into remediation planning"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Define optimization findings output.", purpose="Allow clearer structured output wording.", allowed_operations=["clarify schema"], forbidden_operations=["remove optimization directions"]),
            ],
            validation_commands=["pytest tests/test_module_prompt_upgrade_contracts.py -q"],
        ),
        ModulePromptUpgradeContract(
            prompt_id="upgrade.llm.target_identification",
            module_id="upgrade.llm",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/upgrade/llm/prompt_builders.py",
            prompt_builder_name="build_target_identification_request",
            prompt_builder_symbol="zentex.upgrade.llm.prompt_builders.build_target_identification_request",
            target_component="upgrade.llm.target_identification.prompt",
            immutable_intent="Target identification must prioritize which capabilities and metrics to optimize next from failure history.",
            expected_output_key="findings",
            allowed_prompt_change_scope=["tighten prioritization wording", "clarify findings schema"],
            forbidden_prompt_changes=["must not remove findings array", "must not change prioritization into generic summarization"],
            editable_prompt_sections=["analysis_task", "output_contract"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve target prioritization identity.", purpose="Prevent drift into general analysis.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="analysis_task", mutable=True, intent="Define capability prioritization work.", purpose="Allow clearer ranking instructions.", allowed_operations=["tighten wording"], forbidden_operations=["remove prioritization requirement"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Define findings schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove findings array"]),
            ],
            validation_commands=["pytest tests/test_module_prompt_upgrade_contracts.py -q"],
        ),
    ]


def get_prompt_upgrade_contract(prompt_id: str) -> ModulePromptUpgradeContract:
    contracts = {contract.prompt_id: contract for contract in list_prompt_upgrade_contracts()}
    return contracts[prompt_id]
