from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.memory.enhanced import EnhancedMemoryService  # noqa: E402
from zentex.upgrade.evidence import UpgradeEvidenceService  # noqa: E402
from zentex.upgrade.execution import UpgradeExecutionService  # noqa: E402
from zentex.upgrade.ledger import UpgradeAuditStore, UpgradeMemoryStore  # noqa: E402
from zentex.upgrade.llm.models import LLMUpgradeRequest  # noqa: E402
from zentex.upgrade.llm.runtime import LLMUpgradeRuntime  # noqa: E402
from zentex.upgrade.management import UpgradeLifecycleStatus  # noqa: E402
from zentex.upgrade.models import (  # noqa: E402
    LLMUpgradeIntentRequest,
    PluginEvolutionIntentRequest,
)
from zentex.upgrade.plugin.models import (  # noqa: E402
    PluginCreationRequest,
    PluginEvolutionAction,
    PluginUpgradeRequest,
)
from zentex.upgrade.service import UpgradeFacade  # noqa: E402
from zentex.upgrade.ledger import UpgradeMemoryRecord  # noqa: E402
from zentex.upgrade.management import UpgradeManagementRecord, UpgradeManagementStore, UpgradeTargetKind  # noqa: E402


def test_execution_service_runs_real_llm_runner_and_records_completion() -> None:
    facade = UpgradeFacade()
    facade._llm_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    service = UpgradeExecutionService(
        facade=facade,
        llm_runtime=LLMUpgradeRuntime(
            optimizer_runner=lambda candidate: {
                "status": f"executed:{candidate.candidate_version}"
            }
        ),
    )

    record = service.execute_llm_upgrade(
        LLMUpgradeIntentRequest(
            reason="Provider drift indicates the planner should be re-optimized.",
            change_signals=["quality_regression"],
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
    )

    assert record is not None
    assert record.current_status is UpgradeLifecycleStatus.COMPLETED
    assert record.change_summary == "executed:1.3.0-candidate"


def test_execution_service_persists_real_audit_and_memory_ledgers(
    tmp_path: Path,
) -> None:
    facade = UpgradeFacade()
    facade._llm_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    evidence_service = UpgradeEvidenceService(
        audit_store=UpgradeAuditStore(tmp_path / "upgrade_audit.jsonl"),
        memory_store=UpgradeMemoryStore(tmp_path / "upgrade_memory.jsonl"),
    )
    service = UpgradeExecutionService(
        facade=facade,
        llm_runtime=LLMUpgradeRuntime(
            optimizer_runner=lambda candidate: {
                "status": f"executed:{candidate.candidate_version}"
            }
        ),
        evidence_service=evidence_service,
    )

    record = service.execute_llm_upgrade(
        LLMUpgradeIntentRequest(
            reason="Provider drift indicates the planner should be re-optimized.",
            trace_id="trace-llm-audit-001",
            request_id="request-llm-audit-001",
            source_event_id="signal:provider-drift-001",
            evidence_refs=["datasets/qa.jsonl", "reports/provider_drift.json"],
            change_signals=["quality_regression"],
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
    )

    assert record is not None
    audit_events = evidence_service.audit_store.list_events(record_id=record.record_id)
    memory_records = evidence_service.memory_store.list_records(record_id=record.record_id)
    assert len(audit_events) == 2
    assert audit_events[0].trace_id == "trace-llm-audit-001"
    assert audit_events[0].source_event_id == "signal:provider-drift-001"
    assert audit_events[0].evidence_refs == ["datasets/qa.jsonl", "reports/provider_drift.json"]
    assert len(memory_records) == 2
    assert audit_events[-1].success_stage == "llm_execution"
    assert audit_events[-1].success_summary == "llm_execution completed successfully."
    assert memory_records[-1].reusable_insight is not None
    assert memory_records[-1].success_tags == ["llm", "upgrade", "llm_execution", "success"]
    assert evidence_service.audit_store.file_path is not None
    assert evidence_service.audit_store.file_path.exists()
    assert evidence_service.memory_store.file_path is not None
    assert evidence_service.memory_store.file_path.exists()


def test_execution_service_persists_management_store_and_recovers_records(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "upgrade_management.json"
    store = UpgradeManagementStore(file_path=file_path)
    record = UpgradeManagementRecord(
        record_id="llm-upgrade-persist-001",
        target_kind=UpgradeTargetKind.LLM,
        action="upgrade",
        target_id="reasoning-core",
        title="Persisted planner upgrade",
        reason="Recover upgrade ledger state after restart.",
        trace_id="trace-persist-001",
        request_id="request-persist-001",
        change_summary="Persist upgrade lifecycle state to disk.",
        function_summary="Recover records after restart.",
        previous_version="1.2.3",
        current_version="1.2.3",
        candidate_version="1.3.0-candidate",
        current_status=UpgradeLifecycleStatus.RUNNING,
        current_progress=35,
    )

    store.upsert(record)
    recovered = UpgradeManagementStore(file_path=file_path).get(record.record_id)

    assert file_path.exists()
    assert recovered.record_id == record.record_id
    assert recovered.current_status is UpgradeLifecycleStatus.RUNNING
    assert recovered.current_progress == 35


def test_execution_service_records_memory_recall_context(
    tmp_path: Path,
) -> None:
    enhanced_memory_service = EnhancedMemoryService(
        semantic_store_path=tmp_path / "semantic.jsonl",
        procedural_store_path=tmp_path / "procedural.jsonl",
        episodic_store_path=tmp_path / "episodic.jsonl",
        management_store_path=tmp_path / "management.json",
        audit_store_path=tmp_path / "memory_audit.jsonl",
    )
    enhanced_memory_service.ingest_upgrade_memory_record(
        UpgradeMemoryRecord(
            record_id="llm-memory-ctx-001",
            trace_id="trace-llm-memory-ctx-001",
            request_id="request-llm-memory-ctx-001",
            target_kind="llm",
            action="upgrade",
            target_id="reasoning-core",
            title="Planner validation lesson",
            event_type="llm_upgrade_completed",
            summary="Reuse the validation contract from the last successful planner optimization.",
            current_status="completed",
            current_progress=100,
            previous_version="1.2.2",
            current_version="1.2.3",
            candidate_version="1.3.0-candidate",
            success_stage="llm_execution",
            success_summary="llm_execution completed successfully.",
            reusable_insight="Reuse the validation contract from the last successful planner optimization.",
            success_tags=["llm", "upgrade", "success", "procedure"],
        )
    )
    facade = UpgradeFacade(enhanced_memory_service=enhanced_memory_service)
    facade._llm_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    service = UpgradeExecutionService(
        facade=facade,
        llm_runtime=LLMUpgradeRuntime(
            optimizer_runner=lambda candidate: {
                "status": f"executed:{candidate.candidate_version}"
            }
        ),
    )

    record = service.execute_llm_upgrade(
        LLMUpgradeIntentRequest(
            reason="Provider drift indicates the planner should be re-optimized.",
            trace_id="trace-llm-memory-ctx-001",
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
    )

    assert record is not None
    assert record.recalled_memory_ids
    assert record.memory_recall_query is not None
    assert record.recalled_success_patterns
    assert "Recalled" in str(record.memory_recall_summary)


def test_execution_service_fails_closed_for_plugin_execution_without_real_worker() -> None:
    facade = UpgradeFacade()
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    service = UpgradeExecutionService(facade=facade)

    with pytest.raises(RuntimeError, match="real plugin worker"):
        service.execute_plugin_evolution(
            PluginEvolutionIntentRequest(
                reason="Need publication hook updates.",
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
                    validation_commands=[
                        "pytest tests/runtime/test_cognitive_tool_registry.py -q"
                    ],
                    startup_commands=["uvicorn zentex.web_console.app:app --reload"],
                ),
            )
        )


def test_execution_service_records_structured_failure_knowledge(
    tmp_path: Path,
) -> None:
    facade = UpgradeFacade()
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    evidence_service = UpgradeEvidenceService(
        audit_store=UpgradeAuditStore(tmp_path / "upgrade_audit.jsonl"),
        memory_store=UpgradeMemoryStore(tmp_path / "upgrade_memory.jsonl"),
    )
    service = UpgradeExecutionService(
        facade=facade,
        plugin_worker=lambda _candidate: (_ for _ in ()).throw(
            RuntimeError("validation contract mismatch")
        ),
        evidence_service=evidence_service,
    )
    source_dir = tmp_path / "source_plugin"
    source_dir.mkdir()
    (source_dir / "plugin.py").write_text("print('source')\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="validation contract mismatch"):
        service.execute_plugin_evolution(
            PluginEvolutionIntentRequest(
                reason="Need publication hook updates.",
                requested_action=PluginEvolutionAction.UPGRADE,
                trace_id="trace-plugin-failure-001",
                request_id="request-plugin-failure-001",
                source_event_id="gap:publication-hook-001",
                evidence_refs=["audits/publication_gap.md"],
                upgrade_request=PluginUpgradeRequest(
                    plugin_id="cognitive-tool-router",
                    plugin_path=str(source_dir),
                    baseline_version="0.4.0",
                    goal="Add structured upgrade publication hooks.",
                    allowed_write_paths=[str(source_dir)],
                    validation_commands=[
                        "pytest tests/runtime/test_cognitive_tool_registry.py -q"
                    ],
                    startup_commands=["uvicorn zentex.web_console.app:app --reload"],
                ),
            )
        )

    audit_events = evidence_service.audit_store.list_events()
    failure_event = audit_events[-1]
    assert failure_event.event_type == "plugin_upgrade_failed"
    assert failure_event.failure_stage == "plugin_upgrade"
    assert failure_event.failed_command == "pytest tests/runtime/test_cognitive_tool_registry.py -q"
    assert failure_event.failure_summary == "plugin_upgrade failed with RuntimeError."
    assert failure_event.learning_tags == [
        "plugin",
        "upgrade",
        "plugin_upgrade",
        "runtimeerror",
    ]
    assert failure_event.prevention_hint is not None

def test_execution_service_copies_real_plugin_candidate_before_worker_runs(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source_plugin"
    source_dir.mkdir()
    (source_dir / "plugin.py").write_text("print('source')\n", encoding="utf-8")

    facade = UpgradeFacade()
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    service = UpgradeExecutionService(
        facade=facade,
        plugin_worker=lambda candidate: {
            "status": f"executed:{candidate.candidate_plugin_path}"
        },
    )

    record = service.execute_plugin_evolution(
        PluginEvolutionIntentRequest(
            reason="Need publication hook updates.",
            requested_action=PluginEvolutionAction.UPGRADE,
            upgrade_request=PluginUpgradeRequest(
                plugin_id="cognitive-tool-router",
                plugin_path=str(source_dir),
                baseline_version="0.4.0",
                goal="Add structured upgrade publication hooks.",
                allowed_write_paths=[str(source_dir)],
                validation_commands=["pytest tests/runtime/test_cognitive_tool_registry.py -q"],
                startup_commands=["uvicorn zentex.web_console.app:app --reload"],
            ),
        )
    )

    assert record is not None
    assert record.current_status is UpgradeLifecycleStatus.COMPLETED
    assert record.candidate_path is not None
    candidate_path = Path(record.candidate_path)
    assert candidate_path.exists()
    assert (candidate_path / "plugin.py").read_text(encoding="utf-8") == "print('source')\n"


def test_execution_service_scaffolds_real_plugin_creation_candidate(
    tmp_path: Path,
) -> None:
    facade = UpgradeFacade()
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    service = UpgradeExecutionService(
        facade=facade,
        plugin_worker=lambda candidate: {
            "status": f"executed:{candidate.candidate_plugin_path}"
        },
    )

    record = service.execute_plugin_evolution(
        PluginEvolutionIntentRequest(
            reason="A new plugin is needed for workspace anomaly clustering.",
            requested_action=PluginEvolutionAction.CREATE,
            creation_request=PluginCreationRequest(
                plugin_id="workspace-anomaly-cluster",
                target_root_path=str(tmp_path),
                goal="Create a new plugin for clustering workspace anomalies.",
                validation_commands=["pytest tests/plugins/test_workspace_anomaly_cluster.py -q"],
                startup_commands=["uvicorn zentex.web_console.app:app --reload"],
                requested_capabilities=["llm_reasoning", "workspace_sampling"],
            ),
        )
    )

    assert record is not None
    assert record.current_status is UpgradeLifecycleStatus.COMPLETED
    assert record.candidate_path is not None
    assert Path(record.candidate_path).exists()
