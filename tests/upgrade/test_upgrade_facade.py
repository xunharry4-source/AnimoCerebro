from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.upgrade import UpgradeDecisionAction, UpgradeFacade  # noqa: E402
from zentex.memory.enhanced import EnhancedMemoryService  # noqa: E402
from zentex.upgrade.ledger import UpgradeMemoryRecord  # noqa: E402
from zentex.upgrade.llm.models import LLMUpgradeRequest  # noqa: E402
from zentex.upgrade.models import (  # noqa: E402
    LLMUpgradeIntentRequest,
    PluginEvolutionIntentRequest,
)
from zentex.upgrade.plugin.models import (  # noqa: E402
    PluginCreationRequest,
    PluginEvolutionAction,
    PluginUpgradeRequest,
)


def test_upgrade_facade_skips_llm_upgrade_without_signals() -> None:
    facade = UpgradeFacade()
    request = LLMUpgradeIntentRequest(
        reason="No optimization backlog is present for the current program.",
        upgrade_required=False,
        upgrade_request=LLMUpgradeRequest(
            program_id="reasoning-core",
            target_component="planner",
            baseline_version="1.2.3",
            target_metric="answer_accuracy",
            dataset_refs=["datasets/qa.jsonl"],
            objective_summary="Improve planner accuracy on hard cases.",
            validation_commands=["pytest tests/runtime/test_think_loop.py -q"],
        ),
    )

    decision = facade.plan_llm_upgrade(request)

    assert decision.action is UpgradeDecisionAction.SKIP
    assert decision.candidate is None


def test_upgrade_facade_routes_llm_upgrade_to_dspy_service() -> None:
    facade = UpgradeFacade()
    facade._llm_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    request = LLMUpgradeIntentRequest(
        reason="Provider drift indicates the planner should be re-optimized.",
        change_signals=["quality_regression", "provider_drift"],
        upgrade_request=LLMUpgradeRequest(
            program_id="reasoning-core",
            target_component="planner",
            baseline_version="1.2.3",
            target_metric="answer_accuracy",
            dataset_refs=["datasets/qa.jsonl"],
            objective_summary="Improve planner accuracy on hard cases.",
            validation_commands=["pytest tests/runtime/test_think_loop.py -q"],
        ),
    )

    decision = facade.plan_llm_upgrade(request)

    assert decision.action is UpgradeDecisionAction.UPGRADE
    assert decision.candidate is not None
    assert decision.candidate.candidate_version == "1.3.0-candidate"


def test_upgrade_facade_recalls_managed_memory_before_llm_planning(
    tmp_path: Path,
) -> None:
    enhanced_memory_service = EnhancedMemoryService(
        semantic_store_path=tmp_path / "semantic.jsonl",
        procedural_store_path=tmp_path / "procedural.jsonl",
        episodic_store_path=tmp_path / "episodic.jsonl",
        management_store_path=tmp_path / "management.json",
        audit_store_path=tmp_path / "audit.jsonl",
    )
    enhanced_memory_service.ingest_upgrade_memory_record(
        UpgradeMemoryRecord(
            record_id="llm-memory-001",
            trace_id="trace-memory-001",
            request_id="request-memory-001",
            target_kind="llm",
            action="upgrade",
            target_id="reasoning-core",
            title="Planner optimization learned lesson",
            event_type="llm_upgrade_completed",
            summary="Reuse the planner validation contract when provider drift appears again.",
            current_status="completed",
            current_progress=100,
            previous_version="1.2.2",
            current_version="1.2.3",
            candidate_version="1.3.0-candidate",
            success_stage="llm_execution",
            success_summary="llm_execution completed successfully.",
            reusable_insight="Reuse the planner validation contract when provider drift appears again.",
            success_tags=["llm", "upgrade", "success"],
        )
    )
    facade = UpgradeFacade(enhanced_memory_service=enhanced_memory_service)
    facade._llm_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    request = LLMUpgradeIntentRequest(
        reason="Provider drift indicates the planner should be re-optimized.",
        change_signals=["quality_regression", "provider_drift"],
        trace_id="trace-memory-001",
        upgrade_request=LLMUpgradeRequest(
            program_id="reasoning-core",
            target_component="planner",
            baseline_version="1.2.3",
            target_metric="answer_accuracy",
            dataset_refs=["datasets/qa.jsonl"],
            objective_summary="Improve planner accuracy on hard cases.",
            validation_commands=["pytest tests/runtime/test_think_loop.py -q"],
        ),
    )

    decision = facade.plan_llm_upgrade(request)

    assert decision.action is UpgradeDecisionAction.UPGRADE
    assert decision.memory_context is not None
    assert decision.memory_context.recalled_memory_ids
    assert decision.memory_context.success_patterns
    assert "Recalled" in decision.memory_context.summary


def test_upgrade_facade_routes_plugin_upgrade_to_openhands_service() -> None:
    facade = UpgradeFacade()
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    request = PluginEvolutionIntentRequest(
        reason="The current plugin needs a new publication hook.",
        requested_action=PluginEvolutionAction.UPGRADE,
        upgrade_request=PluginUpgradeRequest(
            plugin_id="cognitive-tool-router",
            plugin_path="src/zentex/runtime/cognitive_tools",
            baseline_version="0.4.0",
            goal="Add structured upgrade publication hooks.",
            allowed_write_paths=[
                "src/zentex/runtime/cognitive_tools",
                "tests/runtime",
            ],
            validation_commands=["pytest tests/runtime/test_cognitive_tool_registry.py -q"],
            startup_commands=["uvicorn zentex.web_console.app:app --reload"],
        ),
    )

    decision = facade.plan_plugin_evolution(request)

    assert decision.action is UpgradeDecisionAction.UPGRADE
    assert decision.upgrade_candidate is not None
    assert decision.upgrade_candidate.candidate_plugin_path != "src/zentex/runtime/cognitive_tools"


def test_upgrade_facade_routes_new_plugin_creation_to_openhands_service() -> None:
    facade = UpgradeFacade()
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    request = PluginEvolutionIntentRequest(
        reason="A new plugin is needed for workspace anomaly clustering.",
        requested_action=PluginEvolutionAction.CREATE,
        creation_request=PluginCreationRequest(
            plugin_id="workspace-anomaly-cluster",
            target_root_path="src/plugins",
            goal="Create a new plugin for clustering workspace anomalies.",
            validation_commands=["pytest tests/plugins/test_workspace_anomaly_cluster.py -q"],
            startup_commands=["uvicorn zentex.web_console.app:app --reload"],
            requested_capabilities=["llm_reasoning", "workspace_sampling"],
        ),
    )

    decision = facade.plan_plugin_evolution(request)

    assert decision.action is UpgradeDecisionAction.CREATE
    assert decision.creation_candidate is not None
    assert decision.creation_candidate.candidate_version == "0.1.1-candidate"
    assert decision.creation_candidate.candidate_plugin_path.startswith("src/plugins/")
