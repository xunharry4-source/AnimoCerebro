from __future__ import annotations

from typing import Any, Dict, List, Optional

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.simulation_spec import (
    SimulationDomainPlugin,
    SimulationIntent,
    SimulationResult,
)


class ThoughtSandbox(SimulationDomainPlugin):
    """
    Built-in generic fallback simulator.

    This sandbox is deterministic and side-effect free. It exists precisely to
    preserve safety when a specialized predictor crashes or times out.
    """

    supported_domains: List[str] = ["general", "system", "cloud", "browser", "code", "market"]

    def simulate_action(
        self,
        intent: SimulationIntent,
        context: Dict[str, Any],
    ) -> SimulationResult:
        predicted_impacts = [
            f"Sandbox predicted effects for {intent.intent_name} in {intent.target_domain}",
            f"Risk level evaluated as {intent.risk_level}",
        ]
        if intent.risk_level.lower() in {"critical", "high"}:
            return SimulationResult(
                is_safe=False,
                predicted_impacts=predicted_impacts,
                veto_reason=f"ThoughtSandbox vetoed high-risk intent: {intent.intent_name}",
                replan_required=True,
                simulated_by=self.plugin_id,
                fallback_used=True,
            )
        return SimulationResult(
            is_safe=True,
            predicted_impacts=predicted_impacts,
            veto_reason=None,
            replan_required=False,
            simulated_by=self.plugin_id,
            fallback_used=True,
        )


class MarketImpactSimulator(SimulationDomainPlugin):
    supported_domains: List[str] = ["market"]

    def simulate_action(
        self,
        intent: SimulationIntent,
        context: Dict[str, Any],
    ) -> SimulationResult:
        symbol = str(intent.intent_payload.get("symbol", "unknown"))
        order_size = float(intent.intent_payload.get("order_size", 0))
        predicted_impacts = [
            f"Estimated slippage for {symbol}",
            f"Estimated position size {order_size}",
        ]
        if order_size > 100000:
            return SimulationResult(
                is_safe=False,
                predicted_impacts=predicted_impacts,
                veto_reason=f"Projected market impact too large for {symbol}",
                replan_required=True,
                simulated_by=self.plugin_id,
            )
        return SimulationResult(
            is_safe=True,
            predicted_impacts=predicted_impacts,
            veto_reason=None,
            replan_required=False,
            simulated_by=self.plugin_id,
        )


class SimulationOrchestrator:
    """
    Domain router for no-side-effects simulation.

    Hard guarantees:
    - specialized domain simulators run in sanitized, execution-free context
    - simulator crashes never escape to the main flow
    - failures degrade to ThoughtSandbox, not to physical execution
    """

    def __init__(
        self,
        *,
        plugins: List[SimulationDomainPlugin],
        fallback_sandbox: ThoughtSandbox,
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


def build_default_thought_sandbox() -> ThoughtSandbox:
    return ThoughtSandbox(
        plugin_id="simulation-thought-sandbox",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sandbox_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


def build_default_market_simulator() -> MarketImpactSimulator:
    return MarketImpactSimulator(
        plugin_id="simulation-market-impact",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["market_prediction_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
