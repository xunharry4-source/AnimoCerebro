from __future__ import annotations

from pathlib import Path
import importlib
import sys
import tempfile

import pytest


fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from zentex.memory.enhanced import EnhancedMemoryService  # noqa: E402
from zentex.upgrade.management import (  # noqa: E402
    UpgradeLifecycleStatus,
    UpgradeManagementRecord,
    UpgradeManagementStore,
    UpgradeTargetKind,
)
from zentex.upgrade.evidence import UpgradeEvidenceService  # noqa: E402
from zentex.upgrade.execution import UpgradeExecutionService  # noqa: E402
from zentex.upgrade.ledger import UpgradeAuditStore, UpgradeMemoryRecord, UpgradeMemoryStore  # noqa: E402
from zentex.upgrade.llm.runtime import LLMUpgradeRuntime  # noqa: E402
from zentex.upgrade.service import UpgradeFacade  # noqa: E402
from zentex.web_console.app import create_web_console_app  # noqa: E402


def _fresh_client() -> TestClient:
    from zentex.web_console import dev_server  # noqa: WPS433

    module = importlib.reload(dev_server)
    return TestClient(module.app)


def _execution_client(*, tmp_path: Path | None = None) -> TestClient:
    root = tmp_path or Path(tempfile.mkdtemp(prefix="zentex-upgrade-api-"))
    enhanced_memory_service = EnhancedMemoryService(
        semantic_store_path=root / "semantic.jsonl",
        procedural_store_path=root / "procedural.jsonl",
        episodic_store_path=root / "episodic.jsonl",
        management_store_path=root / "enhanced_management.json",
        audit_store_path=root / "enhanced_memory_audit.jsonl",
    )
    enhanced_memory_service.ingest_upgrade_memory_record(
        UpgradeMemoryRecord(
            record_id="upgrade-memory-api-001",
            trace_id="upgrade-memory-api-trace-001",
            request_id="upgrade-memory-api-request-001",
            target_kind="llm",
            action="upgrade",
            target_id="reasoning-core",
            title="Planner optimization lesson",
            event_type="llm_upgrade_completed",
            summary="Reuse the previous successful planner validation path during provider drift.",
            current_status="completed",
            current_progress=100,
            previous_version="1.2.2",
            current_version="1.2.3",
            candidate_version="1.3.0-candidate",
            success_stage="llm_execution",
            success_summary="llm_execution completed successfully.",
            reusable_insight="Reuse the previous successful planner validation path during provider drift.",
            success_tags=["llm", "upgrade", "success"],
        )
    )
    facade = UpgradeFacade()
    facade._llm_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    facade._enhanced_memory_service = enhanced_memory_service
    evidence_service = UpgradeEvidenceService(
        audit_store=UpgradeAuditStore(root / "upgrade_audit.jsonl"),
        memory_store=UpgradeMemoryStore(root / "upgrade_memory.jsonl"),
        enhanced_memory_service=enhanced_memory_service,
    )
    execution_service = UpgradeExecutionService(
        facade=facade,
        llm_runtime=LLMUpgradeRuntime(
            optimizer_runner=lambda candidate: {
                "status": f"optimized:{candidate.candidate_version}"
            }
        ),
        plugin_worker=lambda candidate: {
            "status": f"executed:{candidate.candidate_version}"
        },
        evidence_service=evidence_service,
    )
    return TestClient(
        create_web_console_app(
            upgrade_management_store=execution_service.management_store,
            plugin_evolution_runtime=execution_service._plugin_runtime,
            upgrade_execution_service=execution_service,
            enhanced_memory_service=enhanced_memory_service,
        )
    )


def test_upgrade_overview_exposes_llm_and_plugin_counts() -> None:
    client = _fresh_client()

    response = client.get("/api/web/upgrades/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["waiting"] == 1
    assert payload["llm"]["ongoing"] == 1
    assert payload["plugins"]["completed"] == 1
    assert payload["plugins"]["failed"] == 1
    assert {
        item["target_id"] for item in payload["recent_llm"]
    } >= {
        "nine_questions.q1.where_am_i",
        "nine_questions.q4.what_can_i_do",
    }


def test_llm_upgrades_endpoint_filters_ongoing_jobs() -> None:
    client = _fresh_client()

    response = client.get("/api/web/upgrades/llm?lifecycle=ongoing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_kind"] == "llm"
    assert payload["lifecycle"] == "ongoing"
    assert payload["counts"]["ongoing"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["current_status"] == "validating"
    assert payload["items"][0]["candidate_version"] == "1.1.0-candidate"


def test_llm_upgrades_endpoint_filters_waiting_jobs() -> None:
    client = _fresh_client()

    response = client.get("/api/web/upgrades/llm?lifecycle=waiting")

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_kind"] == "llm"
    assert payload["lifecycle"] == "waiting"
    assert payload["counts"]["waiting"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["record_id"] == "llm-upgrade-q4-queue-001"
    assert payload["items"][0]["current_status"] == "queued"


def test_plugin_upgrades_endpoint_can_filter_create_failures() -> None:
    client = _fresh_client()

    response = client.get("/api/web/upgrades/plugins?lifecycle=failed&action=create")

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_kind"] == "plugin"
    assert payload["action_filter"] == "create"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["action"] == "create"
    assert payload["items"][0]["failure_reason"] == (
        "Validation command failed because startup schema was incomplete."
    )


def test_upgrade_record_endpoint_returns_single_record_detail() -> None:
    client = _fresh_client()

    response = client.get("/api/web/upgrades/plugin-upgrade-router-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"] == "plugin-upgrade-router-001"
    assert payload["target_kind"] == "plugin"
    assert payload["current_status"] == "completed"
    assert payload["candidate_path"].endswith("_candidate_0_5_0_candidate")


def test_cancel_upgrade_record_endpoint_transitions_waiting_record() -> None:
    client = _fresh_client()

    response = client.post(
        "/api/web/upgrades/llm-upgrade-q4-queue-001/cancel",
        json={"reason": "Higher-priority rollout is blocking this upgrade."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_status"] == "cancelled"
    assert payload["failure_reason"] == "Higher-priority rollout is blocking this upgrade."


def test_cleanup_failed_candidate_endpoint_transitions_failed_plugin_record() -> None:
    client = _fresh_client()

    response = client.post(
        "/api/web/upgrades/plugin-create-anomaly-001/cleanup-failed-candidate",
        json={"reason": "Failed candidate files were removed after evidence retention."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_status"] == "cleaned_up"
    assert payload["audit_status"] == "cleanup_completed"


def test_cleanup_failed_candidate_endpoint_removes_real_candidate_directory(
    tmp_path: Path,
) -> None:
    candidate_dir = tmp_path / "workspace_anomaly_cluster_candidate"
    candidate_dir.mkdir()
    (candidate_dir / "plugin.py").write_text("print('candidate')\n", encoding="utf-8")

    store = UpgradeManagementStore(
        records=[
            UpgradeManagementRecord(
                record_id="plugin-cleanup-real-001",
                target_kind=UpgradeTargetKind.PLUGIN,
                action="create",
                target_id="workspace-anomaly-cluster",
                title="Workspace anomaly cluster plugin scaffold",
                reason="Cleanup failed candidate after validation failure.",
                trace_id="trace-plugin-cleanup-real-001",
                request_id="request-plugin-cleanup-real-001",
                change_summary="Remove failed candidate directory after evidence retention.",
                function_summary="Delete failed plugin candidate from disk.",
                previous_version=None,
                current_version="0.1.0",
                candidate_version="0.1.1-candidate",
                current_status=UpgradeLifecycleStatus.FAILED,
                current_progress=41,
                failure_reason="Validation failed",
                candidate_path=str(candidate_dir),
                audit_status="failed",
                memory_status="persisted",
            )
        ]
    )
    client = TestClient(create_web_console_app(upgrade_management_store=store))

    response = client.post(
        "/api/web/upgrades/plugin-cleanup-real-001/cleanup-failed-candidate",
        json={"reason": "Removed failed candidate after retaining audit evidence."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_status"] == "cleaned_up"
    assert not candidate_dir.exists()


def test_execute_llm_upgrade_endpoint_runs_real_optimizer_and_records_result() -> None:
    client = _execution_client()

    response = client.post(
        "/api/web/upgrades/llm/execute",
        json={
            "reason": "Planner quality dropped after provider drift.",
            "change_signals": ["quality_regression"],
            "upgrade_request": {
                "program_id": "reasoning-core",
                "target_component": "planner",
                "baseline_version": "1.2.3",
                "target_metric": "answer_accuracy",
                "dataset_refs": ["datasets/qa.jsonl"],
                "objective_summary": "Improve planner accuracy on hard cases.",
                "validation_commands": ["pytest tests/runtime/test_think_loop.py -q"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_kind"] == "llm"
    assert payload["current_status"] == "completed"
    assert payload["candidate_version"] == "1.3.0-candidate"
    assert payload["change_summary"] == "optimized:1.3.0-candidate"
    assert payload["memory_recall_query"] is not None
    assert payload["recalled_memory_ids"]
    assert payload["recalled_success_patterns"]
    assert "Recalled" in payload["memory_recall_summary"]

    audit_response = client.get(f"/api/web/upgrades/{payload['record_id']}/audit-events")
    memory_response = client.get(f"/api/web/upgrades/{payload['record_id']}/memory-records")

    assert audit_response.status_code == 200
    assert memory_response.status_code == 200
    audit_items = audit_response.json()
    memory_items = memory_response.json()
    assert [item["event_type"] for item in audit_items] == [
        "llm_upgrade_started",
        "llm_upgrade_completed",
    ]
    assert all(item["trace_id"] for item in audit_items)
    assert audit_items[-1]["success_stage"] == "llm_execution"
    assert audit_items[-1]["success_summary"] == "llm_execution completed successfully."
    assert memory_items[-1]["event_type"] == "llm_upgrade_completed"
    assert memory_items[-1]["current_status"] == "completed"
    assert memory_items[-1]["reusable_insight"] is not None


def test_execute_plugin_upgrade_endpoint_copies_real_candidate_before_completion(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "router_plugin"
    source_dir.mkdir()
    (source_dir / "plugin.py").write_text("print('router')\n", encoding="utf-8")
    client = _execution_client(tmp_path=tmp_path)

    response = client.post(
        "/api/web/upgrades/plugins/execute",
        json={
            "reason": "Need new publication hooks.",
            "requested_action": "upgrade",
            "upgrade_request": {
                "plugin_id": "cognitive-tool-router",
                "plugin_path": str(source_dir),
                "baseline_version": "0.4.0",
                "goal": "Add structured upgrade publication hooks.",
                "allowed_write_paths": [str(source_dir)],
                "validation_commands": [
                    "pytest tests/runtime/test_cognitive_tool_registry.py -q"
                ],
                "startup_commands": ["uvicorn zentex.web_console.app:app --reload"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_kind"] == "plugin"
    assert payload["action"] == "upgrade"
    assert payload["current_status"] == "completed"
    assert payload["candidate_path"] is not None
    candidate_dir = Path(payload["candidate_path"])
    assert candidate_dir.exists()
    assert (candidate_dir / "plugin.py").read_text(encoding="utf-8") == "print('router')\n"


def test_execute_plugin_creation_endpoint_scaffolds_real_candidate_directory(
    tmp_path: Path,
) -> None:
    client = _execution_client(tmp_path=tmp_path)

    response = client.post(
        "/api/web/upgrades/plugins/execute",
        json={
            "reason": "Need a plugin for workspace anomaly clustering.",
            "requested_action": "create",
            "creation_request": {
                "plugin_id": "workspace-anomaly-cluster",
                "target_root_path": str(tmp_path),
                "goal": "Create a new plugin for clustering workspace anomalies.",
                "validation_commands": [
                    "pytest tests/plugins/test_workspace_anomaly_cluster.py -q"
                ],
                "startup_commands": ["uvicorn zentex.web_console.app:app --reload"],
                "requested_capabilities": ["llm_reasoning", "workspace_sampling"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_kind"] == "plugin"
    assert payload["action"] == "create"
    assert payload["current_status"] == "completed"
    assert payload["candidate_path"] is not None
    assert Path(payload["candidate_path"]).exists()


def test_execute_llm_upgrade_endpoint_fails_closed_without_real_optimizer_runner() -> None:
    facade = UpgradeFacade()
    facade._llm_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    execution_service = UpgradeExecutionService(
        facade=facade,
        evidence_service=UpgradeEvidenceService(
            audit_store=UpgradeAuditStore(),
            memory_store=UpgradeMemoryStore(),
        ),
    )
    client = TestClient(
        create_web_console_app(
            upgrade_management_store=execution_service.management_store,
            plugin_evolution_runtime=execution_service._plugin_runtime,
            upgrade_execution_service=execution_service,
        )
    )

    response = client.post(
        "/api/web/upgrades/llm/execute",
        json={
            "reason": "Planner quality dropped after provider drift.",
            "change_signals": ["quality_regression"],
            "upgrade_request": {
                "program_id": "reasoning-core",
                "target_component": "planner",
                "baseline_version": "1.2.3",
                "target_metric": "answer_accuracy",
                "dataset_refs": ["datasets/qa.jsonl"],
                "objective_summary": "Improve planner accuracy on hard cases.",
                "validation_commands": ["pytest tests/runtime/test_think_loop.py -q"],
            },
        },
    )

    assert response.status_code == 409
    assert "real optimizer runner" in response.json()["detail"]


def test_execute_plugin_upgrade_failure_exposes_structured_failure_knowledge(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "router_plugin"
    source_dir.mkdir()
    (source_dir / "plugin.py").write_text("print('router')\n", encoding="utf-8")
    facade = UpgradeFacade()
    facade._plugin_service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    evidence_service = UpgradeEvidenceService(
        audit_store=UpgradeAuditStore(tmp_path / "upgrade_audit.jsonl"),
        memory_store=UpgradeMemoryStore(tmp_path / "upgrade_memory.jsonl"),
    )
    execution_service = UpgradeExecutionService(
        facade=facade,
        plugin_worker=lambda _candidate: (_ for _ in ()).throw(
            RuntimeError("startup schema mismatch")
        ),
        evidence_service=evidence_service,
    )
    client = TestClient(
        create_web_console_app(
            upgrade_management_store=execution_service.management_store,
            plugin_evolution_runtime=execution_service._plugin_runtime,
            upgrade_execution_service=execution_service,
        )
    )

    response = client.post(
        "/api/web/upgrades/plugins/execute",
        json={
            "reason": "Need new publication hooks.",
            "requested_action": "upgrade",
            "trace_id": "trace-plugin-api-failure-001",
            "request_id": "request-plugin-api-failure-001",
            "source_event_id": "gap:router-hook-001",
            "evidence_refs": ["audits/router_gap.md"],
            "upgrade_request": {
                "plugin_id": "cognitive-tool-router",
                "plugin_path": str(source_dir),
                "baseline_version": "0.4.0",
                "goal": "Add structured upgrade publication hooks.",
                "allowed_write_paths": [str(source_dir)],
                "validation_commands": [
                    "pytest tests/runtime/test_cognitive_tool_registry.py -q"
                ],
                "startup_commands": ["uvicorn zentex.web_console.app:app --reload"],
            },
        },
    )

    assert response.status_code == 409
    records = execution_service.management_store.list_records()
    assert len(records) == 1
    failure_record = records[0]
    assert failure_record.failure_stage == "plugin_upgrade"
    assert failure_record.failed_command == "pytest tests/runtime/test_cognitive_tool_registry.py -q"
    assert failure_record.failure_code == "runtimeerror"
