from __future__ import annotations

from fastapi import FastAPI
import requests

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.web_console.router import api_router


def _real_runtime_app(real_ci_runtime) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    app.state.reflection_service = real_ci_runtime.reflection_service
    app.state.learning_service = real_ci_runtime.learning_service
    app.state.memory_service = real_ci_runtime.memory_service
    app.state.audit_service = real_ci_runtime.audit_service
    app.state.task_service = real_ci_runtime.task_service
    app.state.agent_coordination_service = real_ci_runtime.agent_service
    app.state.agent_service = real_ci_runtime.agent_service
    app.state.default_workspace = "/Users/harry/Documents/git/AnimoCerebro-V2"
    return app


def _module_data(modules_payload: dict, module_id: str) -> dict:
    module = modules_payload["modules"][module_id]
    data = module.get("data")
    return data if isinstance(data, dict) else module


def test_q9_web_run_api_writes_queryable_memory_reflection_audit_and_learning(real_ci_runtime) -> None:
    app = _real_runtime_app(real_ci_runtime)

    with live_http_server(app) as base_url:
        run_response = requests.post(
            f"{base_url}/api/web/nine-questions/q9/run",
            json={"force_refresh": True, "single_only": True},
            timeout=540,
        )
        assert run_response.status_code == 200, run_response.text
        run_payload = run_response.json()
        assert run_payload["started"] is True
        assert run_payload["refresh_reason"] == "single_nine_question_reexecuted:q9"
        assert str(run_payload["trace_id"]).strip()
        assert int(run_payload["snapshot_version"]) >= 1
        assert isinstance(run_payload["revision"], int)

        modules_response = requests.get(
            f"{base_url}/api/web/nine-questions/q9/modules",
            timeout=30,
        )
        assert modules_response.status_code == 200, modules_response.text
        modules_payload = modules_response.json()

        detail_response = requests.get(
            f"{base_url}/api/web/nine-questions/q9",
            timeout=30,
        )
        assert detail_response.status_code == 200, detail_response.text
        detail_payload = detail_response.json()

    assert modules_payload["question_id"] == "q9"
    assert modules_payload["status"]["status"] == "completed"
    module_map = modules_payload["modules"]
    required_modules = {
        "q9_q1_q8_validation",
        "q9_self_model_source_validation",
        "q9_reasoning_budget_source_validation",
        "q9_posture_baseline_projection",
        "q9_posture_control_projection",
        "q9_audit_integration",
        "q9_memory_integration",
        "q9_reflection_integration",
        "q9_learning_integration",
    }
    assert required_modules.issubset(module_map.keys())
    for module_id in required_modules:
        module_entry = module_map[module_id]
        assert module_entry["status"] in {"completed", "ready"}, module_entry
        if module_entry["status"] == "completed":
            assert not str(module_entry.get("error_code") or "").strip(), module_entry
            assert not str(module_entry.get("error_message") or "").strip(), module_entry

    assert detail_payload["question_id"] == "q9"
    context_updates = detail_payload["context_updates"]
    diagnosis = context_updates["q9_execution_diagnosis"]
    assert diagnosis["authenticity_status"] == "completed", diagnosis
    assert diagnosis["used_fallback"] is False

    memory_data = _module_data(modules_payload, "q9_memory_integration")
    memory_id = str(memory_data.get("memory_id") or "").strip()
    memory_trace_id = str(memory_data.get("trace_id") or "").strip()
    assert memory_id
    assert memory_trace_id
    memory_record = real_ci_runtime.memory_service.get_record(memory_id)
    assert memory_record is not None
    assert memory_record.trace_id == memory_trace_id
    memory_rows = real_ci_runtime.memory_service.query_managed_records(trace_id=memory_trace_id, limit=100)
    assert any(item.memory_id == memory_id for item in memory_rows)

    reflection_data = _module_data(modules_payload, "q9_reflection_integration")
    reflection_id = str(reflection_data.get("reflection_id") or "").strip()
    reflection_trace_id = str(reflection_data.get("trace_id") or "").strip()
    assert reflection_id
    assert reflection_trace_id
    reflection_record = real_ci_runtime.reflection_service.get_reflection(reflection_id)
    assert reflection_record is not None
    assert reflection_record.trace_id == reflection_trace_id
    reflection_rows = real_ci_runtime.reflection_service.list_reflections({"trace_id": reflection_trace_id})
    assert any(item.reflection_id == reflection_id for item in reflection_rows)

    audit_data = _module_data(modules_payload, "q9_audit_integration")
    audit_trace_id = str(audit_data.get("trace_id") or "").strip()
    assert audit_trace_id
    audit_flows = real_ci_runtime.audit_service.query_flows(flow_type="nine_questions", limit=200)
    assert any("q9" in str(item).lower() or audit_trace_id in str(item) for item in audit_flows)

    learning_data = _module_data(modules_payload, "q9_learning_integration")
    learning_trace_id = str(learning_data.get("learning_trace_id") or learning_data.get("trace_id") or "").strip()
    assert learning_trace_id
    learning_entries = real_ci_runtime.learning_service.list_history_entries(limit=200)
    assert any("q9" in str(item).lower() or learning_trace_id in str(item) for item in learning_entries)
