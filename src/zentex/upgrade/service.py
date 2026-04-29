from __future__ import annotations

"""
Generic upgrade facade for LLM and plugin evolution.

This file provides the two high-level methods callers use when they do not
want to depend on DSPy or OpenHands specific services directly. The facade
decides whether to skip, upgrade, or create based on explicit intent payloads,
then delegates to the specialized upgrade planners.
"""

from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Union
from zentex.common.storage_paths import get_storage_paths
from zentex.common.prompt_upgrade_contract import ModulePromptUpgradeContract, build_section_policy
from zentex.upgrade.llm.service import DSPyLLMUpgradeService
from zentex.upgrade.models import (
    LLMUpgradeDecision,
    LLMUpgradeIntentRequest,
    PluginEvolutionDecision,
    PluginEvolutionIntentRequest,
)
from zentex.upgrade.plugin.service import OpenHandsPluginUpgradeService
from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.evidence import UpgradeEvidenceService
from zentex.upgrade.management import UpgradeManagementStore
from zentex.upgrade.ledger import UpgradeAuditStore, UpgradeMemoryStore
from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime
from zentex.upgrade.decision import UpgradeDecisionPlanner
from zentex.upgrade.management import (
    FAILED_STATUSES,
    ONGOING_STATUSES,
    WAITING_STATUSES,
    UpgradeLifecycleView,
    UpgradeManagementRecord,
    UpgradeTargetKind,
)
from zentex.upgrade.ledger import UpgradeAuditEvent, UpgradeMemoryRecord
from zentex.upgrade.models import (
    LLMUpgradeRequest,
    PluginEvolutionIntentRequest,
    PluginEvolutionDecision,
    LLMUpgradeIntentRequest,
    LLMUpgradeDecision,
)
from zentex.upgrade.phase_d_self_evolution import (
    activate_phase_d_self_evolution as _activate_phase_d_self_evolution,
    build_phase_d_completion_manifest,
    observe_phase_d_candidate as _observe_phase_d_candidate,
    promote_phase_d_candidate as _promote_phase_d_candidate,
    rollback_phase_d_candidate as _rollback_phase_d_candidate,
)


@dataclass(frozen=True)
class UpgradeRuntimeComponents:
    management_store: UpgradeManagementStore
    plugin_runtime: PluginEvolutionRuntime
    audit_store: UpgradeAuditStore
    memory_store: UpgradeMemoryStore
    evidence_service: UpgradeEvidenceService


def build_default_upgrade_runtime_components(*, memory_service: Optional[Any] = None) -> UpgradeRuntimeComponents:
    runtime_root = get_storage_paths().runtime_data_dir / "upgrade"
    runtime_root.mkdir(parents=True, exist_ok=True)
    audit_store = UpgradeAuditStore(runtime_root / "audit.sqlite3")
    memory_store = UpgradeMemoryStore(runtime_root / "memory.sqlite3")
    return UpgradeRuntimeComponents(
        management_store=UpgradeManagementStore(file_path=runtime_root / "management.sqlite3"),
        plugin_runtime=PluginEvolutionRuntime(),
        audit_store=audit_store,
        memory_store=memory_store,
        evidence_service=UpgradeEvidenceService(
            audit_store=audit_store,
            memory_store=memory_store,
            memory_service=memory_service,
        ),
    )


class UpgradeFacade:
    """Coordinates generic upgrade decisions and delegates concrete planning."""

    def __init__(
        self,
        llm_service: Optional[DSPyLLMUpgradeService] = None,
        plugin_service: Optional[OpenHandsPluginUpgradeService] = None,
        memory_service: Optional[Any] = None,
        execution_service: Optional[UpgradeExecutionService] = None,
    ) -> None:
        self._llm_service = llm_service or DSPyLLMUpgradeService()
        self._plugin_service = plugin_service or OpenHandsPluginUpgradeService()
        self._memory_service = memory_service
        self._decision_planner = UpgradeDecisionPlanner(
            llm_service=self._llm_service,
            plugin_service=self._plugin_service,
            memory_service=memory_service,
        )
        self._execution_service = execution_service or UpgradeExecutionService(
            facade=self,
            evidence_service=UpgradeEvidenceService(
                memory_service=self._memory_service
            )
        )

    def plan_llm_upgrade(self, request: LLMUpgradeIntentRequest) -> LLMUpgradeDecision:
        """Return a generic skip/upgrade decision for LLM optimization."""
        return self._decision_planner.plan_llm_upgrade(request)

    def plan_plugin_evolution(
        self,
        request: PluginEvolutionIntentRequest,
    ) -> PluginEvolutionDecision:
        """Return a generic skip/upgrade/create decision for plugin evolution."""
        return self._decision_planner.plan_plugin_evolution(request)

    def execute_llm_upgrade(self, request: LLMUpgradeIntentRequest) -> Any:
        """Execute a planned LLM upgrade."""
        return self._execution_service.execute_llm_upgrade(request)

    def execute_plugin_evolution(self, request: PluginEvolutionIntentRequest) -> Any:
        """Execute a planned plugin evolution (creation or upgrade)."""
        return self._execution_service.execute_plugin_evolution(request)

    @property
    def execution_service(self) -> UpgradeExecutionService:
        """Access the underlying execution service (Internal use mainly)."""
        return self._execution_service

    def activate_phase_d_self_evolution(
        self,
        *,
        learning_service: Any,
        upgrade_management_store: UpgradeManagementStore,
        record_id: str,
        operator_id: str,
        evidence_refs: list[str],
        shadow_sample_limit: int = 25,
        canary_scope: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return activate_phase_d_self_evolution(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record_id=record_id,
            operator_id=operator_id,
            evidence_refs=evidence_refs,
            shadow_sample_limit=shadow_sample_limit,
            canary_scope=canary_scope,
        )

    def observe_phase_d_candidate(
        self,
        *,
        learning_service: Any,
        upgrade_management_store: UpgradeManagementStore,
        record_id: str,
        operator_id: str,
        evidence_refs: list[str],
        metrics: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return observe_phase_d_candidate(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record_id=record_id,
            operator_id=operator_id,
            evidence_refs=evidence_refs,
            metrics=metrics,
        )

    def promote_phase_d_candidate(
        self,
        *,
        learning_service: Any,
        upgrade_management_store: UpgradeManagementStore,
        record_id: str,
        reviewer_id: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        return promote_phase_d_candidate(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record_id=record_id,
            reviewer_id=reviewer_id,
            evidence_refs=evidence_refs,
        )

    def rollback_phase_d_candidate(
        self,
        *,
        learning_service: Any,
        upgrade_management_store: UpgradeManagementStore,
        record_id: str,
        operator_id: str,
        reason: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        return rollback_phase_d_candidate(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record_id=record_id,
            operator_id=operator_id,
            reason=reason,
            evidence_refs=evidence_refs,
        )

def list_prompt_upgrade_contracts() -> list[ModulePromptUpgradeContract]:
    return [
        ModulePromptUpgradeContract(
            prompt_id="upgrade.ai_executors.plugin_generation",
            module_id="upgrade",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/upgrade/ai_executors_llm_prompt.py",
            prompt_builder_name="build_plugin_generation_request",
            prompt_builder_symbol="zentex.upgrade.ai_executors_llm_prompt.build_plugin_generation_request",
            target_component="upgrade.ai_executors.plugin_generation.prompt",
            immutable_intent="Plugin generation must return plugin.py, test_plugin.py, README.md, and a diff summary for one plugin goal.",
            expected_output_key="plugin_py",
            allowed_prompt_change_scope=["tighten artifact schema", "compress goal framing"],
            forbidden_prompt_changes=["must not remove plugin_py", "must not remove test_plugin_py", "must not remove readme_md"],
            editable_prompt_sections=["goal", "required_artifacts", "output_contract"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve plugin generation identity.", purpose="Prevent drift into analysis or review.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="goal", mutable=True, intent="Provide plugin objective.", purpose="Allow concise goal framing.", allowed_operations=["compress evidence"], forbidden_operations=["change plugin goal"]),
                build_section_policy(section_key="required_artifacts", mutable=True, intent="Define required files.", purpose="Allow artifact wording clarification.", allowed_operations=["tighten wording"], forbidden_operations=["remove required artifact"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce artifact json schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove plugin_py", "remove test_plugin_py", "remove readme_md"]),
            ],
            validation_commands=["pytest tests/test_module_prompt_upgrade_contracts.py -q"],
        )
    ]


def get_prompt_upgrade_contract(prompt_id: str) -> ModulePromptUpgradeContract:
    contracts = {contract.prompt_id: contract for contract in list_prompt_upgrade_contracts()}
    return contracts[prompt_id]


def activate_phase_d_self_evolution(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    operator_id: str,
    evidence_refs: list[str],
    shadow_sample_limit: int = 25,
    canary_scope: Optional[list[str]] = None,
) -> dict[str, Any]:
    return _activate_phase_d_self_evolution(
        learning_service=learning_service,
        upgrade_management_store=upgrade_management_store,
        record_id=record_id,
        operator_id=operator_id,
        evidence_refs=evidence_refs,
        shadow_sample_limit=shadow_sample_limit,
        canary_scope=canary_scope,
    )


def observe_phase_d_candidate(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    operator_id: str,
    evidence_refs: list[str],
    metrics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return _observe_phase_d_candidate(
        learning_service=learning_service,
        upgrade_management_store=upgrade_management_store,
        record_id=record_id,
        operator_id=operator_id,
        evidence_refs=evidence_refs,
        metrics=metrics,
    )


def promote_phase_d_candidate(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    reviewer_id: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return _promote_phase_d_candidate(
        learning_service=learning_service,
        upgrade_management_store=upgrade_management_store,
        record_id=record_id,
        reviewer_id=reviewer_id,
        evidence_refs=evidence_refs,
    )


def rollback_phase_d_candidate(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    operator_id: str,
    reason: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return _rollback_phase_d_candidate(
        learning_service=learning_service,
        upgrade_management_store=upgrade_management_store,
        record_id=record_id,
        operator_id=operator_id,
        reason=reason,
        evidence_refs=evidence_refs,
    )


__all__ = [
    "UpgradeFacade",
    "UpgradeExecutionService",
    "UpgradeEvidenceService",
    "UpgradeManagementStore",
    "UpgradeManagementRecord",
    "UpgradeLifecycleView",
    "UpgradeTargetKind",
    "FAILED_STATUSES",
    "ONGOING_STATUSES",
    "WAITING_STATUSES",
    "UpgradeAuditStore",
    "UpgradeMemoryStore",
    "UpgradeAuditEvent",
    "UpgradeMemoryRecord",
    "PluginEvolutionRuntime",
    "LLMUpgradeRequest",
    "LLMUpgradeIntentRequest",
    "LLMUpgradeDecision",
    "PluginEvolutionIntentRequest",
    "PluginEvolutionDecision",
    "activate_phase_d_self_evolution",
    "observe_phase_d_candidate",
    "promote_phase_d_candidate",
    "rollback_phase_d_candidate",
    "build_phase_d_completion_manifest",
]
