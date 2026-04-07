from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from plugins.simulation.base_simulation_bus import (  # noqa: E402
    MarketImpactSimulator,
    SimulationOrchestrator,
    ThoughtSandbox,
)
from zentex.core.plugin_base import (  # noqa: E402
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.core.simulation_spec import (  # noqa: E402
    SimulationIntent,
    SimulationResult,
)


class CrashingMarketSimulator(MarketImpactSimulator):
    def simulate_action(
        self,
        intent: SimulationIntent,
        context: dict[str, object],
    ) -> SimulationResult:
        raise TimeoutError("predictor crashed")


def _build_thought_sandbox() -> ThoughtSandbox:
    return ThoughtSandbox(
        plugin_id="simulation-thought-sandbox",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sandbox_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


def _build_market_simulator() -> MarketImpactSimulator:
    return MarketImpactSimulator(
        plugin_id="simulation-market-impact",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["market_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


def _build_crashing_market_simulator() -> CrashingMarketSimulator:
    return CrashingMarketSimulator(
        plugin_id="simulation-market-crashing",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["market_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


def test_domain_predictor_crash_falls_back_to_thought_sandbox() -> None:
    orchestrator = SimulationOrchestrator(
        plugins=[_build_crashing_market_simulator()],
        fallback_sandbox=_build_thought_sandbox(),
    )

    result = orchestrator.simulate(
        SimulationIntent(
            intent_name="rebalance_portfolio",
            target_domain="market",
            intent_payload={"symbol": "BTC", "order_size": 5000},
            risk_level="medium",
        ),
        context={"portfolio": {"cash": 10000}},
    )

    assert result.fallback_used is True
    assert result.simulated_by == "simulation-thought-sandbox"
    assert result.predicted_impacts


def test_high_risk_simulation_veto_requires_replan() -> None:
    orchestrator = SimulationOrchestrator(
        plugins=[],
        fallback_sandbox=_build_thought_sandbox(),
    )

    result = orchestrator.simulate(
        SimulationIntent(
            intent_name="wipe_production_cluster",
            target_domain="system",
            intent_payload={"cluster": "prod-eu-1"},
            risk_level="critical",
        ),
        context={"workspace": "/tmp"},
    )

    assert result.is_safe is False
    assert result.replan_required is True
    assert result.veto_reason is not None
    assert "wipe_production_cluster" in result.veto_reason


def test_simulation_context_strips_physical_execution_handles() -> None:
    sandbox = _build_thought_sandbox()
    sandbox_simulate = Mock(wraps=sandbox.simulate_action)
    object.__setattr__(sandbox, "simulate_action", sandbox_simulate)
    orchestrator = SimulationOrchestrator(
        plugins=[],
        fallback_sandbox=sandbox,
    )

    dangerous_context = {
        "workspace": "/tmp",
        "http_post": Mock(name="http_post"),
        "system_write": Mock(name="system_write"),
        "shell_execute": Mock(name="shell_execute"),
        "safe_note": "simulate only",
    }
    orchestrator.simulate(
        SimulationIntent(
            intent_name="draft_plan",
            target_domain="general",
            intent_payload={"goal": "prepare summary"},
            risk_level="low",
        ),
        context=dangerous_context,
    )

    passed_context = sandbox_simulate.call_args.args[1]
    assert "http_post" not in passed_context
    assert "system_write" not in passed_context
    assert "shell_execute" not in passed_context
    assert passed_context["safe_note"] == "simulate only"
