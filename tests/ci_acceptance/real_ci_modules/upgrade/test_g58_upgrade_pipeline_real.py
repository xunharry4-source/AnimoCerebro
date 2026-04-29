from __future__ import annotations

from contextlib import contextmanager
import inspect
import socket
import threading

import pytest
import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.upgrade.base_models import UpgradeTargetKind
from zentex.upgrade.management import (
    UpgradeLifecycleStatus,
    UpgradeManagementRecord,
)
from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime
from zentex.upgrade.service import UpgradeFacade


@contextmanager
def _live_http_server(app: FastAPI):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        pass
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_g58_upgrade_facade_is_thin_and_business_logic_lives_outside_service() -> None:
    source = inspect.getsource(UpgradeFacade)
    assert "_recall_memory_context" not in source
    assert "_build_llm_memory_context" not in source
    assert "_build_plugin_memory_context" not in source
    assert "success_patterns.append" not in source
    assert "failure_patterns.append" not in source
    assert "should_upgrade" not in source
    assert "resolve_plugin_evolution_action" not in source


def test_g58_llm_plan_api_returns_real_candidate_without_live_primitive_for_prompt_optimization(
    acceptance_app: FastAPI,
    tmp_path,
) -> None:
    suffix = unique_suffix()
    prompt_file = tmp_path / f"prompt_{suffix}.py"
    prompt_file.write_text(
        "from zentex.common.prompt_builder import build_prompt_section\n\n"
        "def build_request():\n"
        "    return build_prompt_section(\n"
        "        key='goal',\n"
        "        title='Goal',\n"
        "        intent='Keep goal stable.',\n"
        "        purpose='Test prompt upgrade planning.',\n"
        "        content='old goal wording',\n"
        "    )\n",
        encoding="utf-8",
    )
    payload = {
        "reason": f"real prompt optimization plan {suffix}",
        "upgrade_required": True,
        "change_signals": ["prompt_regression"],
        "upgrade_request": {
            "program_id": f"q8-objective-{suffix}",
            "target_component": "q8_objective_deriver.prompt",
            "baseline_version": "1.2.0",
            "target_metric": "factuality",
            "dataset_refs": [f"dataset-ref-{suffix}"],
            "objective_summary": "tighten prompt section while preserving intent",
            "validation_commands": ["python -m py_compile prompt.py"],
            "upgrade_kind": "prompt_optimization",
            "prompt_file_path": str(prompt_file),
            "prompt_builder_symbol": "tests.prompt.build_request",
            "immutable_intent": "Q8 objective prompt intent must stay stable.",
            "prompt_contract": {
                "editable_prompt_sections": ["goal"],
                "immutable_prompt_sections": [],
                "section_change_policy": [],
            },
            "forbidden_prompt_changes": ["must not remove goal"],
            "allowed_prompt_change_scope": ["tighten wording"],
        },
    }

    with _live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/upgrade/llm/plan",
            json=payload,
            timeout=60,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action"] == "upgrade"
    assert body["candidate"]["program_id"] == f"q8-objective-{suffix}"
    assert body["candidate"]["candidate_version"] == "1.3.0-candidate"
    assert body["candidate"]["execution_plan"]["provider"] == "dspy"
    assert body["candidate"]["execution_plan"]["metadata"]["upgrade_kind"] == "prompt_optimization"
    assert body["candidate"]["execution_plan"]["metadata"]["prompt_file_path"] == str(prompt_file)
    assert body["candidate"]["dspy_signature"] is None
    assert body["candidate"]["dspy_module"] is None


def test_g58_llm_promote_and_rollback_api_performs_query_and_physical_restore(
    acceptance_app: FastAPI,
    tmp_path,
) -> None:
    suffix = unique_suffix()
    store = acceptance_app.state.upgrade_management_store
    prompt_file = tmp_path / f"active_prompt_{suffix}.py"
    backup_file = tmp_path / f"backup_prompt_{suffix}.py"
    baseline_text = "PROMPT_VERSION = 'baseline'\n"
    candidate_text = "PROMPT_VERSION = 'candidate'\n"
    prompt_file.write_text(candidate_text, encoding="utf-8")
    backup_file.write_text(baseline_text, encoding="utf-8")
    record = UpgradeManagementRecord(
        record_id=f"g58-llm-record-{suffix}",
        target_kind=UpgradeTargetKind.LLM,
        action="upgrade",
        target_id=f"q8-objective-{suffix}",
        title=f"G58 LLM upgrade {suffix}",
        reason="real promote rollback api test",
        trace_id=f"g58-llm-trace-{suffix}",
        request_id=f"g58-llm-request-{suffix}",
        change_summary="candidate prompt exists on disk",
        function_summary="verify promote and physical rollback",
        previous_version="1.2.0",
        current_version="1.2.0",
        candidate_version="1.3.0-candidate",
        current_status=UpgradeLifecycleStatus.COMPLETED,
        current_progress=100,
        source_path=str(prompt_file),
        backup_path=str(backup_file),
        payload={"candidate_prompt_bundle": {"updated_file": str(prompt_file)}},
    )
    store.upsert(record)

    with _live_http_server(acceptance_app) as base_url:
        promote = requests.post(
            f"{base_url}/api/web/upgrade/llm/promote",
            json={
                "record_id": record.record_id,
                "reason": f"reviewed real candidate {suffix}",
                "reviewer_id": f"reviewer-{suffix}",
                "evidence_refs": [f"evidence-promote-{suffix}"],
            },
            timeout=60,
        )
        promoted_query = requests.get(
            f"{base_url}/api/web/upgrades/{record.record_id}",
            timeout=60,
        )
        rollback = requests.post(
            f"{base_url}/api/web/upgrade/llm/rollback",
            json={
                "record_id": record.record_id,
                "reason": f"rollback rehearsal {suffix}",
                "operator_id": f"operator-{suffix}",
                "evidence_refs": [f"evidence-rollback-{suffix}"],
            },
            timeout=60,
        )
        rolled_back_query = requests.get(
            f"{base_url}/api/web/upgrades/{record.record_id}",
            timeout=60,
        )
        audit_events = requests.get(
            f"{base_url}/api/web/upgrades/{record.record_id}/audit-events",
            timeout=60,
        )

    assert promote.status_code == 200, promote.text
    assert promote.json()["current_status"] == "active"
    assert promote.json()["current_version"] == "1.3.0-candidate"
    assert promoted_query.status_code == 200, promoted_query.text
    assert promoted_query.json()["payload"]["promotion_decision"]["reviewer_id"] == f"reviewer-{suffix}"
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["current_status"] == "rolled_back"
    assert rolled_back_query.json()["current_status"] == "rolled_back"
    assert store.get(record.record_id).current_status == UpgradeLifecycleStatus.ROLLED_BACK
    assert prompt_file.read_text(encoding="utf-8") == baseline_text
    event_types = {item["event_type"] for item in audit_events.json()}
    assert "llm_upgrade_promoted" in event_types
    assert "llm_upgrade_rolled_back" in event_types


def test_g58_plugin_plan_and_run_api_fail_closed_without_openhands_and_persist_no_fake_record(
    acceptance_app: FastAPI,
    tmp_path,
) -> None:
    suffix = unique_suffix()
    plugin_dir = tmp_path / f"source_plugin_{suffix}"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text('{"name": "source", "version": "1.0.0"}', encoding="utf-8")
    (plugin_dir / "plugin.py").write_text("def execute():\n    return 'ok'\n", encoding="utf-8")
    payload = {
        "reason": f"real plugin evolution fail closed {suffix}",
        "requested_action": "upgrade",
        "change_signals": ["plugin_gap"],
        "upgrade_request": {
            "plugin_id": f"g58-plugin-{suffix}",
            "plugin_path": str(plugin_dir),
            "baseline_version": "1.0.0",
            "goal": "add bounded read-only comparison capability",
            "allowed_write_paths": [str(tmp_path)],
            "validation_commands": ["python -m py_compile plugin.py"],
            "startup_commands": ["python -m py_compile plugin.py"],
            "requested_capabilities": ["read_only_compare"],
        },
    }

    with _live_http_server(acceptance_app) as base_url:
        plan = requests.post(
            f"{base_url}/api/web/upgrade/plugin/plan",
            json=payload,
            timeout=60,
        )
        run = requests.post(
            f"{base_url}/api/web/upgrade/plugin/run",
            json=payload,
            timeout=60,
        )
        candidates = requests.get(
            f"{base_url}/api/web/upgrade/plugin/candidates",
            timeout=60,
        )

    assert plan.status_code == 409, plan.text
    assert "OpenHands SDK is not installed" in plan.json()["detail"]
    assert run.status_code == 409, run.text
    assert "OpenHands SDK is not installed" in run.json()["detail"]
    assert candidates.status_code == 200, candidates.text
    assert f"g58-plugin-{suffix}" not in {item["target_id"] for item in candidates.json()["items"]}
    assert not any(path.name.startswith(f"source_plugin_{suffix}_candidate") for path in tmp_path.iterdir())


def test_g58_plugin_runtime_rejects_forbidden_side_effects_in_real_candidate(tmp_path) -> None:
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "plugin.py").write_text(
        "import requests\n\n"
        "def execute():\n"
        "    return requests.get('https://example.invalid').text\n",
        encoding="utf-8",
    )
    runtime = PluginEvolutionRuntime()

    with pytest.raises(RuntimeError) as exc_info:
        runtime.validate_worker_evidence(
            worker_result={"status": "worker-finished", "health_probe_results": [{"success": True}]},
            candidate_path=str(candidate_dir),
            commands=[],
        )

    assert "Forbidden import 'requests'" in str(exc_info.value)
