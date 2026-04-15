from __future__ import annotations

from typing import Any, Dict, List

from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.simulation import (
    SimulationDomainPlugin,
    SimulationIntent,
    SimulationResult,
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


def build_default_market_simulator() -> MarketImpactSimulator:
    return MarketImpactSimulator(
        plugin_id="simulation-market-impact",
        version="1.0.0",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["market_prediction_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


MarketImpactSimulator.model_rebuild()
