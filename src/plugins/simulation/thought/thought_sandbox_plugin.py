from __future__ import annotations

from typing import Any, Dict, List

from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.simulation import (
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

    supported_domains: List[str] = ["cognitive", "resource", "memory", "system", "general"]

    def simulate_action(
        self,
        intent: SimulationIntent,
        context: Dict[str, Any],
    ) -> SimulationResult:
        """
        Policy: Eradicate Circular Logic.
        Perform authentic Tool-Conflict Audit and Resource Prediction.
        """
        payload = intent.intent_payload
        intent_name = intent.intent_name
        target_domain = intent.target_domain
        
        # 1. Authentic Conflict Detection (No Echo)
        # Check for contradictory execution requirements in the payload
        tools = payload.get("tools", [])
        constraints = payload.get("constraints", [])
        
        predicted_impacts = [
            f"Simulating cognitive path for: {intent_name}",
            f"Target Domain: {target_domain}",
        ]
        
        is_safe = True
        veto_reason = None
        replan_required = False
        
        # Heuristic: Detect isolation vs network conflicts
        has_network_req = any("network" in str(c).lower() for c in constraints)
        has_isolation_req = any("isolation" in str(c).lower() for c in constraints)
        
        if has_network_req and has_isolation_req:
            is_safe = False
            veto_reason = "COGNITIVE CONFLICT: Action requires both Network Access and Isolation."
            replan_required = True
            predicted_impacts.append("CRITICAL: Mutually exclusive constraints detected.")

        # 2. Resource & Impact Prediction (Authentic Calculation)
        # - Entropy: Complexity increases with number of tools and constraints
        # - Congestion: Overlap in required capabilities
        
        entropy = min(1.0, len(tools) * 0.15 + len(constraints) * 0.1)
        
        # Capability analyze for congestion (Problem 1 Fix)
        # Any shared capability requirements increase cognitive impact and risk
        all_caps = set()
        for t in tools:
            if isinstance(t, dict):
                all_caps.update(t.get("required_capabilities", []))
        
        congestion = min(1.0, len(all_caps) * 0.12)
        
        resource_usage = round((entropy * 0.6 + congestion * 0.4), 2)
        cognitive_impact = round(entropy * 0.4, 2)
        
        predicted_impacts.append(f"Entropy Analysis: {len(tools)} tools, {len(constraints)} constraints (Score: {entropy:.2f})")
        predicted_impacts.append(f"Capability Congestion: {len(all_caps)} unique capabilities (Score: {congestion:.2f})")
        
        if resource_usage > 0.75:
            predicted_impacts.append(f"WARNING: High resource depletion predicted ({resource_usage*100:.1f}%)")
            if not veto_reason:
                is_safe = False
                veto_reason = f"RESOURCE DEPLETION: Complexity score {resource_usage} exceeds sandbox threshold."
                replan_required = True

        return SimulationResult(
            is_safe=is_safe,
            predicted_impacts=predicted_impacts,
            cognitive_impact=cognitive_impact,
            resource_usage=resource_usage,
            risk_score=round(0.8 + resource_usage * 0.2 if not is_safe else resource_usage * 0.4, 2),
            veto_reason=veto_reason,
            replan_required=replan_required,
            simulated_by=self.plugin_id,
        )


def build_default_thought_sandbox() -> ThoughtSandbox:
    return ThoughtSandbox(
        plugin_id="simulation-thought-sandbox",
        version="1.0.0",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sandbox_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


ThoughtSandbox.model_rebuild()
