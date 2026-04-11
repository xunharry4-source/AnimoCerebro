from __future__ import annotations

from typing import Any, Dict, List

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
