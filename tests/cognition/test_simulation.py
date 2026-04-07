from __future__ import annotations

from pathlib import Path
import sys
import time
from unittest import mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.model_provider_spec import ModelProviderRateLimitError  # noqa: E402
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus  # noqa: E402
from zentex.core.simulation_spec import SimulationDomainPlugin, SimulationIntent, SimulationResult  # noqa: E402
from zentex.cognition.simulation import (  # noqa: E402
    CounterfactualSimulationEngine,
    StaleSimulationResultError,
)


class FastGeneralSimulator(SimulationDomainPlugin):
    supported_domains: list[str] = ["general"]
    branch_label_prefix: str = "general"

    def simulate_action(
        self,
        intent: SimulationIntent,
        context: dict[str, object],
    ) -> SimulationResult:
        return SimulationResult(
            is_safe=True,
            predicted_impacts=[f"{self.branch_label_prefix}:{intent.intent_name}"],
            veto_reason=None,
            replan_required=False,
            simulated_by=self.plugin_id,
        )


class SlowGeneralSimulator(FastGeneralSimulator):
    def simulate_action(
        self,
        intent: SimulationIntent,
        context: dict[str, object],
    ) -> SimulationResult:
        time.sleep(0.1)
        return super().simulate_action(intent, context)


def _build_plugin(plugin_id: str, plugin_cls: type[FastGeneralSimulator], *, prefix: str) -> FastGeneralSimulator:
    return plugin_cls(
        plugin_id=plugin_id,
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["simulation_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        branch_label_prefix=prefix,
    )


def test_simulation_engine_discards_stale_background_result() -> None:
    model_provider = mock.Mock()
    model_provider.generate_json.return_value = {
        "summary": "choose branch-a",
        "risk_ranking": [{"branch_id": "branch-a", "risk_score": 0.2, "rank": 1}],
        "recommended_branch_id": "branch-a",
    }
    engine = CounterfactualSimulationEngine(
        model_provider=model_provider,
        simulation_plugins=[_build_plugin("sim-slow", SlowGeneralSimulator, prefix="slow")],
    )
    future = engine.submit_simulation(
        goal_id="goal-stale",
        branches=[
            {
                "branch_id": "branch-a",
                "branch_label": "A",
                "target_domain": "general",
                "intent_name": "stabilize",
            }
        ],
        snapshot_version=0,
        idempotency_key="idem-stale",
        base_context={},
    )
    engine.bump_snapshot_version()

    with pytest.raises(StaleSimulationResultError, match="Discarded stale simulation result"):
        future.result(timeout=2)

    assert engine.get_bundle("goal-stale") is None


def test_simulation_engine_fail_closed_when_llm_is_rate_limited() -> None:
    model_provider = mock.Mock()
    model_provider.generate_json.side_effect = ModelProviderRateLimitError("429")
    engine = CounterfactualSimulationEngine(
        model_provider=model_provider,
        simulation_plugins=[_build_plugin("sim-fast", FastGeneralSimulator, prefix="fast")],
    )

    future = engine.submit_simulation(
        goal_id="goal-llm-fail",
        branches=[
            {
                "branch_id": "branch-a",
                "branch_label": "A",
                "target_domain": "general",
                "intent_name": "stabilize",
            }
        ],
        snapshot_version=0,
        idempotency_key="idem-llm",
        base_context={},
    )

    with pytest.raises(ModelProviderRateLimitError, match="429"):
        future.result(timeout=2)


def test_simulation_engine_collects_parallel_plugin_results_into_bundle() -> None:
    model_provider = mock.Mock()
    model_provider.generate_json.return_value = {
        "summary": "branch-a is safest",
        "risk_ranking": [{"branch_id": "branch-a", "risk_score": 0.2, "rank": 1}],
        "recommended_branch_id": "branch-a",
    }
    engine = CounterfactualSimulationEngine(
        model_provider=model_provider,
        simulation_plugins=[
            _build_plugin("sim-fast-a", FastGeneralSimulator, prefix="simA"),
            _build_plugin("sim-fast-b", FastGeneralSimulator, prefix="simB"),
        ],
    )

    bundle = engine.submit_simulation(
        goal_id="goal-merge",
        branches=[
            {
                "branch_id": "branch-a",
                "branch_label": "A",
                "target_domain": "general",
                "intent_name": "stabilize",
            }
        ],
        snapshot_version=0,
        idempotency_key="idem-merge",
        base_context={},
    ).result(timeout=2)

    assert len(bundle.branches) == 2
    assert {branch.simulated_by[0] for branch in bundle.branches} == {"sim-fast-a", "sim-fast-b"}
    assert bundle.outcome_comparison is not None
    assert bundle.outcome_comparison.recommended_branch_id == "branch-a"
    _, kwargs = model_provider.generate_json.call_args
    assert "scenario_branches" in kwargs["context"]
    assert "snapshot_version" not in kwargs["context"]
