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
    UpgradeMemoryContext,
    UpgradeDecisionAction,
)
from zentex.upgrade.plugin.models import PluginEvolutionAction
from zentex.upgrade.plugin.service import OpenHandsPluginUpgradeService
from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.evidence import UpgradeEvidenceService
from zentex.upgrade.management import UpgradeManagementStore
from zentex.upgrade.ledger import UpgradeAuditStore, UpgradeMemoryStore
from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime
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
        self._execution_service = execution_service or UpgradeExecutionService(
            facade=self,
            evidence_service=UpgradeEvidenceService(
                memory_service=self._memory_service
            )
        )

    def plan_llm_upgrade(self, request: LLMUpgradeIntentRequest) -> LLMUpgradeDecision:
        """Return a generic skip/upgrade decision for LLM optimization."""
        memory_context = self._build_llm_memory_context(request)

        should_upgrade = (
            request.upgrade_required
            if request.upgrade_required is not None
            else bool(request.change_signals)
        )
        if not should_upgrade:
            return LLMUpgradeDecision(
                action=UpgradeDecisionAction.SKIP,
                rationale=(
                    "No LLM upgrade was scheduled because the caller did not mark "
                    "the optimization as required and provided no change signals."
                ),
                candidate=None,
                memory_context=memory_context,
            )

        candidate = self._llm_service.plan_candidate(request.upgrade_request)
        return LLMUpgradeDecision(
            action=UpgradeDecisionAction.UPGRADE,
            rationale=request.reason,
            candidate=candidate,
            memory_context=memory_context,
        )

    def plan_plugin_evolution(
        self,
        request: PluginEvolutionIntentRequest,
    ) -> PluginEvolutionDecision:
        """Return a generic skip/upgrade/create decision for plugin evolution."""
        memory_context = self._build_plugin_memory_context(request)

        action = self._resolve_plugin_action(request)
        if action is None:
            return PluginEvolutionDecision(
                action=UpgradeDecisionAction.SKIP,
                rationale=(
                    "No plugin evolution was scheduled because the caller did not "
                    "request an upgrade or plugin creation."
                ),
                memory_context=memory_context,
            )

        if action is PluginEvolutionAction.CREATE:
            creation_candidate = self._plugin_service.plan_new_candidate(
                request.creation_request
            )
            return PluginEvolutionDecision(
                action=UpgradeDecisionAction.CREATE,
                rationale=request.reason,
                creation_candidate=creation_candidate,
                memory_context=memory_context,
            )

        upgrade_candidate = self._plugin_service.plan_candidate(request.upgrade_request)
        return PluginEvolutionDecision(
            action=UpgradeDecisionAction.UPGRADE,
            rationale=request.reason,
            upgrade_candidate=upgrade_candidate,
            memory_context=memory_context,
        )

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

    def _resolve_plugin_action(
        self,
        request: PluginEvolutionIntentRequest,
    ) -> Optional[PluginEvolutionAction]:
        if request.requested_action is not None:
            return request.requested_action
        if request.creation_request is not None and request.upgrade_request is None:
            return PluginEvolutionAction.CREATE
        if request.upgrade_request is not None:
            return PluginEvolutionAction.UPGRADE
        if any(signal.lower() == "create_plugin" for signal in request.change_signals):
            return PluginEvolutionAction.CREATE
        if request.change_signals:
            return PluginEvolutionAction.UPGRADE
        return None

    def _build_llm_memory_context(
        self,
        request: LLMUpgradeIntentRequest,
    ) -> Optional[UpgradeMemoryContext]:
        return self._recall_memory_context(
            query_parts=[
                request.reason,
                *request.change_signals,
                request.upgrade_request.program_id,
                request.upgrade_request.target_component,
                request.upgrade_request.target_metric,
                request.upgrade_request.objective_summary,
            ],
            target_id=request.upgrade_request.program_id,
            trace_id=request.trace_id,
        )

    def _build_plugin_memory_context(
        self,
        request: PluginEvolutionIntentRequest,
    ) -> Optional[UpgradeMemoryContext]:
        if request.upgrade_request is not None:
            return self._recall_memory_context(
                query_parts=[
                    request.reason,
                    *request.change_signals,
                    request.upgrade_request.plugin_id,
                    request.upgrade_request.goal,
                ],
                target_id=request.upgrade_request.plugin_id,
                trace_id=request.trace_id,
            )
        if request.creation_request is not None:
            return self._recall_memory_context(
                query_parts=[
                    request.reason,
                    *request.change_signals,
                    request.creation_request.plugin_id,
                    request.creation_request.goal,
                    *request.creation_request.requested_capabilities,
                ],
                target_id=request.creation_request.plugin_id,
                trace_id=request.trace_id,
            )
        return None

    def _recall_memory_context(
        self,
        *,
        query_parts: list[str],
        target_id: Optional[str],
        trace_id: Optional[str],
    ) -> Optional[UpgradeMemoryContext]:
        if self._memory_service is None:
            return None
        query = " ".join(part.strip() for part in query_parts if part and part.strip())
        query_variants = [
            variant
            for variant in [
                target_id,
                " ".join(part.strip() for part in query_parts[:3] if part and part.strip()),
                query,
            ]
            if variant and variant.strip()
        ]
        if not query_variants:
            return None
        hits = []
        selected_query = query_variants[0]
        for variant in query_variants:
            hits = self._memory_service.recall(
                query=variant,
                limit=8,
                trace_id=trace_id,
                target_id=target_id,
            )
            selected_query = variant
            if hits:
                break
        if not hits:
            return UpgradeMemoryContext(
                query=query,
                summary="No managed memory matched the current upgrade objective.",
            )

        success_patterns: list[str] = []
        failure_patterns: list[str] = []
        suspect_patterns: list[str] = []
        recalled_ids: list[str] = []
        for hit in hits:
            recalled_ids.append(hit.memory_id)
            managed = self._memory_service.get_record(hit.memory_id)
            lowered_tags = {tag.lower() for tag in hit.tags}
            summary = hit.summary.strip()
            if managed is not None:
                status = managed.status.lower()
                trust = managed.trust_level.lower()
                if status in {"rejected", "archived"} or trust in {"suspect", "rejected"}:
                    suspect_patterns.append(summary)
                    continue
            if (
                "success" in lowered_tags
                or "procedure" in lowered_tags
                or "reusable" in summary.lower()
            ):
                success_patterns.append(summary)
            elif (
                "failed" in summary.lower()
                or "failure" in summary.lower()
                or "error" in summary.lower()
                or any(tag.endswith("error") for tag in lowered_tags)
            ):
                failure_patterns.append(summary)
            else:
                success_patterns.append(summary)

        summary_bits: list[str] = []
        if success_patterns:
            summary_bits.append(f"{len(success_patterns)} reusable success memories")
        if failure_patterns:
            summary_bits.append(f"{len(failure_patterns)} failure patterns")
        if suspect_patterns:
            summary_bits.append(f"{len(suspect_patterns)} suspect memories")
        return UpgradeMemoryContext(
            query=selected_query,
            recalled_memory_ids=recalled_ids,
            success_patterns=success_patterns[:3],
            failure_patterns=failure_patterns[:3],
            suspect_patterns=suspect_patterns[:3],
            summary=(
                "Recalled " + ", ".join(summary_bits) + " before planning."
                if summary_bits
                else "Managed memory recall returned context but no reusable pattern classification was derived."
            ),
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
]
