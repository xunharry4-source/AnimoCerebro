from __future__ import annotations

"""Top-level upgrade decision planning."""

from typing import Any, Optional

from zentex.upgrade.llm.service import DSPyLLMUpgradeService
from zentex.upgrade.memory_context import (
    UpgradeMemoryContextResolver,
    resolve_plugin_evolution_action,
)
from zentex.upgrade.models import (
    LLMUpgradeDecision,
    LLMUpgradeIntentRequest,
    PluginEvolutionDecision,
    PluginEvolutionIntentRequest,
    UpgradeDecisionAction,
)
from zentex.upgrade.plugin.models import PluginEvolutionAction
from zentex.upgrade.plugin.service import OpenHandsPluginUpgradeService


class UpgradeDecisionPlanner:
    """Plans skip/upgrade/create decisions for upgrade facade callers."""

    def __init__(
        self,
        *,
        llm_service: DSPyLLMUpgradeService,
        plugin_service: OpenHandsPluginUpgradeService,
        memory_service: Optional[Any] = None,
    ) -> None:
        self._llm_service = llm_service
        self._plugin_service = plugin_service
        self._memory_context_resolver = UpgradeMemoryContextResolver(memory_service)

    def plan_llm_upgrade(self, request: LLMUpgradeIntentRequest) -> LLMUpgradeDecision:
        memory_context = self._memory_context_resolver.for_llm_request(request)
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
        memory_context = self._memory_context_resolver.for_plugin_request(request)
        action = resolve_plugin_evolution_action(request)
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
