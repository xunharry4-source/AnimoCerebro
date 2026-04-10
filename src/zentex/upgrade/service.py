from __future__ import annotations

"""
Generic upgrade facade for LLM and plugin evolution.

This file provides the two high-level methods callers use when they do not
want to depend on DSPy or OpenHands specific services directly. The facade
decides whether to skip, upgrade, or create based on explicit intent payloads,
then delegates to the specialized upgrade planners.
"""

from typing import Any, Optional
from zentex.memory import EnhancedMemoryService
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


class UpgradeFacade:
    """Coordinates generic upgrade decisions and delegates concrete planning."""

    def __init__(
        self,
        llm_service: DSPyLLMUpgradeService | None = None,
        plugin_service: OpenHandsPluginUpgradeService | None = None,
        enhanced_memory_service: EnhancedMemoryService | None = None,
        execution_service: UpgradeExecutionService | None = None,
    ) -> None:
        self._llm_service = llm_service or DSPyLLMUpgradeService()
        self._plugin_service = plugin_service or OpenHandsPluginUpgradeService()
        self._enhanced_memory_service = enhanced_memory_service
        self._execution_service = execution_service or UpgradeExecutionService(
            facade=self,
            evidence_service=UpgradeEvidenceService(
                enhanced_memory_service=self._enhanced_memory_service
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
    ) -> PluginEvolutionAction | None:
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
    ) -> UpgradeMemoryContext | None:
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
    ) -> UpgradeMemoryContext | None:
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
        target_id: str | None,
        trace_id: str | None,
    ) -> UpgradeMemoryContext | None:
        if self._enhanced_memory_service is None:
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
            hits = self._enhanced_memory_service.recall(
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
            managed = self._enhanced_memory_service.get_managed_record(hit.memory_id)
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
