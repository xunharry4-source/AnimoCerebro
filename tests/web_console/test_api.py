from __future__ import annotations

from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest


fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from plugins.nine_questions import build_q1_where_am_i_plugin  # noqa: E402
from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec  # noqa: E402
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus  # noqa: E402
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptStore  # noqa: E402
from zentex.web_console.app import create_web_console_app  # noqa: E402
from zentex.web_console.services.plugins import build_managed_plugin_record  # noqa: E402
from zentex.web_console import dev_server  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptEntryType  # noqa: E402


def _fresh_client() -> TestClient:
    module = importlib.reload(dev_server)
    return TestClient(module.app)


class FakeSandboxProvider(ModelProviderSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "model_provider"

    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        return {
            "primary_domain": "sandbox_console",
            "secondary_domains": ["web_console"],
            "confidence": 0.97,
            "reasoning_summary": "sandbox inference",
            "uncertainties": ["mock context only"],
            "suggested_first_step": "inspect sandbox output",
        }

    def health_probe(self) -> PluginHealthStatus:
        return PluginHealthStatus.HEALTHY


def test_overview_returns_runtime_snapshot() -> None:
    client = _fresh_client()

    response = client.get("/api/web/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"]["runtime_id"]
    assert payload["runtime"]["transcript_store_status"] == "ready"
    assert payload["working_memory"]["current_focus_summary"]
    assert payload["metacognition"]["scheduler_status"] == "polling_transcript"
    assert payload["active_weight_plugin_id"] == "default_conservative_weight"
    assert payload["weight_fallback_occurred"] is True
    assert payload["weight_profile"]["active_weight_plugin_id"] == "default_conservative_weight"


def test_nine_questions_endpoint_reads_runtime_state_snapshots() -> None:
    client = _fresh_client()

    response = client.get("/api/web/nine-questions/latest-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "web-console"
    assert payload["snapshot_version"] >= 9
    assert len(payload["questions"]) == 9
    q1 = next(item for item in payload["questions"] if item["question_id"] == "q1")
    assert q1["tool_id"] == "nine_questions.q1"
    assert q1["summary"]
    assert q1["context_updates"]["environment_description"]
    q9 = next(item for item in payload["questions"] if item["question_id"] == "q9")
    assert q9["trace_id"] == "seed-nine-q9"


def test_latest_report_returns_initializing_for_real_empty_session(tmp_path) -> None:
    runtime = BrainRuntime(runtime_id="empty-runtime", transcript_store=BrainTranscriptStore(tmp_path / "empty.jsonl"))
    session = runtime.create_session("empty-session")
    runtime.set_nine_question_bootstrap_status(
        "initializing",
        trace_id="startup-cold-start",
    )
    app = create_web_console_app(runtime=runtime, session=session)
    client = TestClient(app)

    response = client.get("/api/web/nine-questions/latest-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "initializing"
    assert payload["status_message"] == "大脑冷启动中：正在执行全量九问推演..."
    assert payload["questions"] == []


def test_tasks_endpoint_reads_real_task_service_state() -> None:
    client = _fresh_client()

    response = client.get("/api/web/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 3
    assert all(item["task_id"] for item in payload)
    assert all(item["idempotency_key"] for item in payload)
    assert any(item["title"] == "校验九问真实状态绑定" for item in payload)


def test_agents_endpoint_aggregates_inbox_assigned_goal_and_receipts() -> None:
    client = _fresh_client()

    response = client.get("/api/web/agents")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 3
    build_bot = next(item for item in payload if item["agent_id"] == "agent-build")
    assert build_bot["assigned_goal"] == "校验九问真实状态绑定"
    assert build_bot["inbox"] == []
    audit_bot = next(item for item in payload if item["agent_id"] == "agent-audit")
    assert audit_bot["inbox"]
    assert audit_bot["inbox"][0]["idempotency_key"] == "seed-task-002"
    memory_bot = next(item for item in payload if item["agent_id"] == "agent-memory")
    assert memory_bot["receipts"]
    assert memory_bot["receipts"][0]["title"] == "归档任务执行回执"


def test_mcp_servers_endpoint_returns_runtime_server_states() -> None:
    client = _fresh_client()

    response = client.get("/api/web/mcp-servers")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 2
    knowledge = next(item for item in payload if item["server_id"] == "knowledge-hub")
    assert knowledge["transport_type"] == "stdio"
    assert knowledge["status"] == "online"
    assert knowledge["tool_count"] == 1
    assert knowledge["tools"][0]["mapped_domain"] == "cognitive"
    ops = next(item for item in payload if item["server_id"] == "ops-bridge")
    assert ops["tools"][0]["mapped_domain"] == "execution"
    assert ops["tools"][0]["requires_cloud_audit"] is True


def test_nine_question_sandbox_endpoint_does_not_pollute_production_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_FAKE_KEY", "sandbox-secret")

    production_store = BrainTranscriptStore(tmp_path / "production_transcript.jsonl")
    runtime = BrainRuntime(runtime_id="sandbox-runtime", transcript_store=production_store)
    session = runtime.create_session("sandbox-session")
    state = runtime.nine_question_state
    state.current_context.update(
        {
            "workspace_structure_analysis": {"top_level_dirs": ["src", "tests"]},
            "workspace_content_samples": {
                "sampled_file_summaries": [{"path": "src/main.py", "summary": "runtime entry"}]
            },
            "environment_event": {"kind": "web_console"},
            "physical_host_state": {"cwd": "/tmp/sandbox"},
        }
    )
    state.apply_question_result(
        question_id="q1",
        tool_id="nine_questions.q1",
        summary="生产态原始结果",
        confidence=0.51,
        context_updates={"environment_description": "production baseline"},
        trace_id="prod-trace-q1",
        refresh_reason="seed",
        driver_refs=["seed:q1"],
    )
    revision_before = state.revision
    production_snapshot_before = dict(state.question_snapshots["q1"])

    registry_store = BrainTranscriptStore(tmp_path / "registry_transcript.jsonl")
    registry = CognitiveToolRegistry(transcript_store=registry_store)
    q1_plugin = build_q1_where_am_i_plugin()
    registry.register(q1_plugin, description="sandbox q1")
    registry.promote_plugin(q1_plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "test promote")
    registry.promote_plugin(q1_plugin.plugin_id, PluginLifecycleStatus.ACTIVE, "test activate")

    provider = FakeSandboxProvider(
        plugin_id="fake-sandbox-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sandbox-provider-regression"],
        revocation_reasons=["manual revoke"],
        provider_name="fake-sandbox-provider",
        api_base="https://sandbox.invalid",
        api_key_env="TEST_FAKE_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )

    app = create_web_console_app(
        cognitive_tool_registry=registry,
        runtime=runtime,
        session=session,
        managed_plugins=[build_managed_plugin_record(provider)],
    )
    client = TestClient(app)

    production_store.write_entry = MagicMock(side_effect=AssertionError("production transcript write_entry called"))
    production_store.append_entry = MagicMock(side_effect=AssertionError("production transcript append_entry called"))
    production_store.append = MagicMock(side_effect=AssertionError("production transcript append called"))

    response = client.post(
        "/api/web/nine-questions/q1/test",
        json={
            "mock_context": {
                "environment_event": {"kind": "sandbox_run"},
                "physical_host_state": {
                    "cwd": "/tmp/sandbox",
                    "memory_pressure": "high",
                    "network_health": "degraded",
                },
                "workspace_structure_analysis": {
                    "directory_hierarchy_summary": "src/, logs/, data/",
                    "top_level_dirs": ["src", "logs", "data"],
                    "file_total_count": 12,
                    "suffix_distribution": {".py": 6, ".md": 3, ".log": 2},
                    "high_frequency_filename_keywords": {"api": 3, "invoice": 1},
                    "candidate_groups": ["python_code", "logs"],
                    "obvious_risk_files": ["data/invoices.csv"],
                },
                "workspace_content_samples": {
                    "sampled_file_summaries": [
                        {
                            "path": "README.md",
                            "summary": "sandbox-only sample",
                            "snippet": "ERROR sandbox validation failed on line 1",
                        }
                    ],
                    "log_anomaly_snippets": ["ERROR sandbox validation failed on line 1"],
                },
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["question_id"] == "q1"
    assert payload["tool_id"] == "nine-question-q1-where-am-i"
    assert payload["provider_name"] == "fake-sandbox-provider"
    assert payload["prompt"]
    assert payload["result"]["primary_domain"] == "sandbox_console"
    assert payload["context_updates"]["workspace_domain_inference"]["suggested_first_step"] == "inspect sandbox output"
    assert payload["preprocessed_evidence"]["physical_and_environment"]["environment_event"]["kind"] == "sandbox_run"
    assert payload["preprocessed_evidence"]["physical_and_environment"]["memory_pressure"] == "high"
    assert payload["preprocessed_evidence"]["physical_and_environment"]["network_health_status"] == "degrade"
    assert payload["preprocessed_evidence"]["workspace_structure"]["file_total_count"] == 12
    assert payload["preprocessed_evidence"]["workspace_structure"]["suffix_distribution"][".py"] == 6
    assert payload["preprocessed_evidence"]["workspace_structure"]["candidate_group_details"][0]["label"] == "python_code"
    assert payload["preprocessed_evidence"]["workspace_content_sampling"]["sampled_file_summaries"][0]["path"] == "README.md"
    assert payload["preprocessed_evidence"]["workspace_content_sampling"]["sample_count"] == 1
    assert payload["preprocessed_evidence"]["workspace_content_sampling"]["long_text_evidence"][0]["kind"] == "summary"
    assert payload["inference_result"]["primary_domain"] == "sandbox_console"
    assert payload["inference_result"]["suggested_first_step"] == "inspect sandbox output"

    assert production_store.write_entry.call_count == 0
    assert production_store.append_entry.call_count == 0
    assert production_store.append.call_count == 0
    assert state.revision == revision_before
    assert state.question_snapshots["q1"] == production_snapshot_before


def test_cognitive_plugins_returns_real_registry_state() -> None:
    client = _fresh_client()

    response = client.get("/api/web/plugins/cognitive")

    assert response.status_code == 200
    payload = response.json()
    tool_ids = [item["tool_id"] for item in payload]

    assert "risk-comparator" in tool_ids
    assert "evidence-ranker" in tool_ids
    degraded_item = next(item for item in payload if item["tool_id"] == "evidence-ranker")
    assert degraded_item["status"] == "degraded"
    assert degraded_item["failure_count"] == 3
    assert degraded_item["rollback_conditions"]


def test_events_stream_pushes_transcript_events() -> None:
    client = _fresh_client()
    runtime = client.app.state.runtime

    with client.websocket_connect("/api/web/events/stream") as websocket:
        runtime.transcript_store.write_entry(
            session_id="web-console",
            turn_id="turn-stream-default",
            entry_type=BrainTranscriptEntryType.WORKING_MEMORY_UPDATED,
            payload={"current_focus_summary": "default stream delta"},
            source="diagnostic_test",
            trace_id="stream-default-trace",
        )
        message = websocket.receive_json()

    assert message["type"] == "transcript_event"
    assert message["event"]["trace_id"] == "stream-default-trace"
    assert message["event"]["entry_type"] == BrainTranscriptEntryType.WORKING_MEMORY_UPDATED.value
    assert message["overview"]["runtime"]["runtime_id"]


def test_events_stream_with_cursor_only_pushes_new_entries() -> None:
    client = _fresh_client()
    runtime = client.app.state.runtime
    existing_entries = list(runtime.transcript_store.iter_entries())
    assert existing_entries
    last_entry_id = existing_entries[-1].entry_id

    with client.websocket_connect(f"/api/web/events/stream?last_entry_id={last_entry_id}") as websocket:
        runtime.transcript_store.write_entry(
            session_id="web-console",
            turn_id="turn-stream-test",
            entry_type=BrainTranscriptEntryType.WORKING_MEMORY_UPDATED,
            payload={"current_focus_summary": "stream delta"},
            source="diagnostic_test",
            trace_id="stream-delta-trace",
        )
        message = websocket.receive_json()

    assert message["type"] == "transcript_event"
    assert message["event"]["trace_id"] == "stream-delta-trace"
    assert message["event"]["entry_type"] == BrainTranscriptEntryType.WORKING_MEMORY_UPDATED.value


def test_model_provider_audit_endpoint_returns_llm_trace() -> None:
    client = _fresh_client()

    response = client.get("/api/web/audit/model-provider")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    first_trace = payload[0]
    assert first_trace["trace_id"] == "turn-bootstrap:phase_2_frame"
    assert first_trace["request_id"]
    assert first_trace["decision_id"]
    assert first_trace["phase_name"] == "phase_2_frame"
    assert first_trace["source_module"] == "ThinkLoop"
    assert first_trace["invocation_phase"] == "phase_2_frame"
    assert first_trace["question_driver_refs"]
    assert first_trace["prompt"]
    assert first_trace["context"]
    assert first_trace["request_driver"]["nine_question_inputs"]
    assert first_trace["request_driver"]["question_driver_refs"]
    assert first_trace["result"]["role_hypothesis"] == "operator"
    assert first_trace["related_events"]
    assert any(event["entry_type"] == "context_snapshot_written" for event in first_trace["related_events"])


def test_replay_endpoint_returns_trace_chain_payload() -> None:
    client = _fresh_client()

    response = client.get("/api/web/replay/turn-bootstrap:phase_2_frame")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "turn-bootstrap:phase_2_frame"
    assert payload["source_module"] == "ThinkLoop"
    assert payload["invocation_phase"] == "phase_2_frame"
    assert payload["question_driver_refs"]
    assert payload["events"]
    assert any(event["entry_type"] == "model_provider_invoked" for event in payload["events"])


def test_turn_audit_endpoint_returns_turn_milestones() -> None:
    client = _fresh_client()

    response = client.get("/api/web/audit/turns?page=1&page_size=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert any(item["turn_id"] == "turn-bootstrap" for item in payload["items"])


def test_turn_replay_endpoint_returns_cross_trace_events() -> None:
    client = _fresh_client()

    response = client.get("/api/web/replay/turn/turn-bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["turn_id"] == "turn-bootstrap"
    assert payload["events"]
    assert payload["trace_groups"]
    assert any(event["entry_type"] == BrainTranscriptEntryType.TURN_STARTED.value for event in payload["events"])


def test_turn_replay_endpoint_can_omit_payloads() -> None:
    client = _fresh_client()

    response = client.get("/api/web/replay/turn/turn-bootstrap?include_payload=false")

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"]
    first_event = payload["events"][0]
    assert isinstance(first_event.get("payload"), dict)
    assert first_event["payload"].get("omitted") is True


def test_interventions_endpoint_writes_audited_human_intervention() -> None:
    client = _fresh_client()

    response = client.post(
        "/api/web/interventions",
        json={
            "action": "manual_confirm",
            "reason": "operator adjusted role framing",
            "idempotency_key": "manual-confirm-001",
            "operator_id": "tester-1",
            "phase_name": "phase_2_frame",
            "manual_context_patch": {"role_hint": "human reviewer"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["operator_id"] == "tester-1"
    assert payload["idempotency_key"] == "manual-confirm-001"
    assert payload["trace_id"] == "intervention:manual-confirm-001"
    assert payload["control_state"]["last_action"] == "manual_confirm"
    assert payload["control_state"]["manual_context_patch"]["role_hint"] == "human reviewer"

    replay_response = client.get("/api/web/replay/intervention:manual-confirm-001")
    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    assert any(event["entry_type"] == "human_intervention_applied" for event in replay_payload["events"])
    intervention_event = next(
        event for event in replay_payload["events"] if event["entry_type"] == "human_intervention_applied"
    )
    assert intervention_event["payload"]["operator_id"] == "tester-1"
    assert intervention_event["payload"]["idempotency_key"] == "manual-confirm-001"
    assert intervention_event["payload"]["manual_context_patch"]["role_hint"] == "human reviewer"
    assert any(event["entry_type"] == "working_memory_updated" for event in replay_payload["events"])


def test_interventions_endpoint_is_idempotent_for_duplicate_keys() -> None:
    client = _fresh_client()
    idempotency_key = f"reject-001-{datetime.now(timezone.utc).timestamp()}"

    payload = {
        "action": "reject_action",
        "reason": "duplicate should not replay",
        "idempotency_key": idempotency_key,
        "operator_id": "tester-2",
        "phase_name": "phase_2_frame",
        "manual_context_patch": {"current_focus": "review evidence"},
    }

    first_response = client.post("/api/web/interventions", json=payload)
    second_response = client.post("/api/web/interventions", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["trace_id"] == second_response.json()["trace_id"]
    assert first_response.json()["control_state"] == second_response.json()["control_state"]
    assert first_response.json()["idempotent_replay"] is False
    assert second_response.json()["idempotent_replay"] is True

    replay_response = client.get(f"/api/web/replay/intervention:{idempotency_key}")
    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    intervention_events = [
        event for event in replay_payload["events"] if event["entry_type"] == "human_intervention_applied"
    ]
    assert len(intervention_events) == 1


def test_cognitive_agenda_endpoint_returns_runtime_temporal_state() -> None:
    client = _fresh_client()

    response = client.get("/api/web/cognitive-agenda")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["state_id"]
    assert payload["items"]
    assert any(item["status"] in {"watching", "blocked", "review_now", "overdue"} for item in payload["items"])
    assert all("next_review_condition" in item for item in payload["items"])


def test_cognitive_conflicts_endpoint_returns_unresolved_conflicts() -> None:
    client = _fresh_client()

    response = client.get("/api/web/cognitive-conflicts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["conflicts"]
    assert any(conflict["severity"] == "critical" for conflict in payload["conflicts"])


def test_simulation_endpoint_returns_structured_bundle() -> None:
    client = _fresh_client()

    response = client.get("/api/web/simulations/goal-runtime-stability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["bundle"]["goal_id"] == "goal-runtime-stability"
    assert len(payload["bundle"]["branches"]) >= 2
    assert payload["bundle"]["outcome_comparison"]["recommended_branch_id"]


def test_interaction_mind_endpoint_returns_structured_state() -> None:
    client = _fresh_client()

    response = client.get("/api/web/interaction-mind/web-console")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["entity_id"] == "web-console"
    assert payload["state"]["communication_fit"]["preferred_style"] == "evidence_first"
    assert payload["state"]["misunderstanding_signals"]


def test_consolidation_cycles_endpoint_returns_structured_history() -> None:
    client = _fresh_client()

    response = client.get("/api/web/memory/consolidation-cycles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cycles"]
    first_cycle = payload["cycles"][0]
    assert first_cycle["cycle_id"]
    assert first_cycle["input_refs"]
    assert first_cycle["summary"]
    assert first_cycle["promotion_candidates"]


def test_audits_endpoint_returns_paginated_audit_history() -> None:
    client = _fresh_client()
    runtime = client.app.state.runtime

    for index in range(10):
        runtime.transcript_store.write_entry(
            session_id="audit-test-session",
            turn_id=f"audit-turn-{index}",
            entry_type=BrainTranscriptEntryType.HUMAN_INTERVENTION_APPLIED,
            payload={
                "action": "manual_confirm",
                "reason": f"audit-{index}",
                "operator_id": "tester",
            },
            source="diagnostic_test",
            trace_id=f"audit-trace-{index}",
        )

    response = client.get("/api/web/audits?page=1&page_size=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 5
    assert payload["total_items"] >= 10
    assert payload["total_pages"] >= 2
    assert len(payload["items"]) == 5


def test_audits_endpoint_filters_by_decision_and_request_id() -> None:
    client = _fresh_client()
    runtime = client.app.state.runtime

    runtime.transcript_store.write_entry(
        session_id="audit-filter-session",
        turn_id="audit-filter-turn-1",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-filter-hit",
            "decision_id": "decision-filter-hit",
            "caller_context": {"decision_id": "decision-filter-hit"},
        },
        source="diagnostic_test",
        trace_id="trace-filter-hit",
    )
    runtime.transcript_store.write_entry(
        session_id="audit-filter-session",
        turn_id="audit-filter-turn-2",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-filter-miss",
            "decision_id": "decision-filter-miss",
            "caller_context": {"decision_id": "decision-filter-miss"},
        },
        source="diagnostic_test",
        trace_id="trace-filter-miss",
    )

    response = client.get(
        "/api/web/audits?page=1&page_size=50&request_id=req-filter-hit&decision_id=decision-filter-hit"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert all(item["trace_id"] == "trace-filter-hit" for item in payload["items"])
