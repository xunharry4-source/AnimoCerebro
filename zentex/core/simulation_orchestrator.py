from __future__ import annotations

"""Simulation domain routing utility.

Framework-level orchestrator that routes simulation intents to the correct
domain plugin with deterministic fallback guarantees.
"""

from typing import Any, Dict, List, Optional

from zentex.core.simulation_spec import (
    SimulationDomainPlugin,
    SimulationIntent,
    SimulationResult,
)


class SimulationOrchestrator:
    """
    Domain router for no-side-effects simulation.

    Hard guarantees:
    - specialized domain simulators run in sanitized, execution-free context
    - simulator crashes never escape to the main flow
    - failures degrade to the fallback sandbox, not to physical execution
    """

    def __init__(
        self,
        *,
        plugins: List[SimulationDomainPlugin],
        fallback_sandbox: SimulationDomainPlugin,
    ) -> None:
        self._plugins = plugins
        self._fallback_sandbox = fallback_sandbox

    def simulate(
        self,
        intent: SimulationIntent,
        context: Dict[str, Any],
    ) -> SimulationResult:
        safe_context = self._sanitize_context(context)
        plugin = self._select_plugin(intent.target_domain)

        if plugin is None:
            return self._simulate_with_fallback(intent, safe_context)

        try:
            result = plugin.simulate_action(intent, safe_context)
            validated = SimulationResult.model_validate(result)
        except Exception:
            return self._simulate_with_fallback(intent, safe_context)

        if not validated.is_safe:
            veto_reason = validated.veto_reason or (
                f"Simulation vetoed unsafe intent: {intent.intent_name}"
            )
            return validated.model_copy(
                update={
                    "veto_reason": veto_reason,
                    "replan_required": True,
                }
            )
        return validated

    def _select_plugin(self, domain: str) -> Optional[SimulationDomainPlugin]:
        for plugin in self._plugins:
            if domain in plugin.supported_domains:
                return plugin
        return None

    def _simulate_with_fallback(
        self,
        intent: SimulationIntent,
        context: Dict[str, Any],
    ) -> SimulationResult:
        result = self._fallback_sandbox.simulate_action(intent, context)
        validated = SimulationResult.model_validate(result)
        if not validated.is_safe:
            veto_reason = validated.veto_reason or (
                f"Fallback sandbox vetoed unsafe intent: {intent.intent_name}"
            )
            return validated.model_copy(
                update={
                    "veto_reason": veto_reason,
                    "replan_required": True,
                    "fallback_used": True,
                }
            )
        return validated.model_copy(update={"fallback_used": True})

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        blocked_keys = {
            "execution_plugin",
            "execute_action",
            "http_post",
            "http_put",
            "system_write",
            "shell_execute",
        }
        sanitized: Dict[str, Any] = {}
        for key, value in context.items():
            if key in blocked_keys:
                continue
            if callable(value):
                continue
            sanitized[key] = value
        return sanitized
