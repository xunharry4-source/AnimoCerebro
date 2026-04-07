from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from plugins.nine_questions.q4_what_can_i_do.q4_what_can_i_do_plugin import (  # noqa: E402
    build_q4_what_can_i_do_plugin,
)
from zentex.core.model_provider_spec import (  # noqa: E402
    ModelProviderAuthError,
    ModelProviderCallerContext,
    ModelProviderSpec,
)
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus  # noqa: E402
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore  # noqa: E402
from zentex.web_console.app import create_web_console_app  # noqa: E402
from zentex.web_console.services.plugins import build_managed_plugin_record  # noqa: E402


class StaticQ4Provider(ModelProviderSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "model_provider"

    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        return {
            "capability_boundary_profile": {
                "capability_upper_limits": ["read_workspace_state", "inspect_audit_log"],
                "actionable_space": ["view_dashboard", "inspect_audit_log"],
                "executable_strategies": [
                    "Use read-only inspection workflow.\nStep 1: inspect logs.\nStep 2: collect evidence.",
                    "Escalate to human operator for any missing write capability.",
                ],
            }
        }

    def health_probe(self) -> PluginHealthStatus:
        return PluginHealthStatus.HEALTHY


class AuthFailingQ4Provider(StaticQ4Provider):
    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        raise ModelProviderAuthError("provider rejected supplied API key")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_q4_runtime_client(provider: ModelProviderSpec, tmp_path: Path) -> tuple[TestClient, BrainRuntime]:
    production_transcript = BrainTranscriptStore(tmp_path / "production_transcript.jsonl")
    runtime = BrainRuntime(runtime_id="q4-runtime", transcript_store=production_transcript)
    session = runtime.create_session("q4-session")
    state = session.current_nine_question_state
    state.current_context.update(
        {
            "q1_scene_model": {
                "primary_domain": "audit_console",
                "secondary_domains": ["ops_workspace"],
                "environment_type": "console",
            },
            "q1_uncertainty_profile": {
                "uncertainty_intensity": 0.44,
                "risk_sources": ["network_jitter"],
            },
            "q2_role_profile": {
                "identity_role": "zentex",
                "active_role": "auditor",
                "task_role": "capability_assessor",
            },
            "q2_mission_boundary": {
                "current_mission": "determine safe actions",
                "continuity_boundaries": ["do_not_fake_capability"],
            },
            "q3_unified_asset_inventory": {
                "available_cognitive_tools": ["MemorySearch", "CodeAnalyzer"],
                "available_execution_tools": [],
                "connected_agents": [
                    {"agent_id": "agent-online", "name": "AuditAgent", "summary": "read-only audit helper", "status": "online"},
                    {"agent_id": "agent-offline", "name": "OfflineAgent", "summary": "offline", "status": "offline"},
                ],
                "activated_strategy_patches": ["Patch-v3: disallow write path"],
                "accessible_workspace_zones": ["/workspace/audit", "/workspace/reports"],
                "permissions": {"mode": "read_only"},
            },
            "q3_resource_evaluation": {
                "resource_status": "degraded",
                "missing_critical_assets": ["WRITE_EXECUTOR"],
                "bottleneck_node": "execution_tools",
            },
            "q4_capability_boundary_profile": {
                "capability_upper_limits": ["read_workspace_state", "inspect_audit_log"],
                "actionable_space": ["view_dashboard", "inspect_audit_log"],
                "executable_strategies": [
                    "Use read-only inspection workflow.\nStep 1: inspect logs.\nStep 2: collect evidence.",
                    "Escalate to human operator for any missing write capability.",
                ],
            },
        }
    )
    state.apply_question_result(
        question_id="q4",
        tool_id="nine_questions.q4",
        summary="actionable=2; strategies=2",
        confidence=0.88,
        context_updates={"q4_capability_boundary_profile": state.current_context["q4_capability_boundary_profile"]},
        trace_id="trace-q4-production",
        refresh_reason="unit_test",
        driver_refs=["我能做什么"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q4-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q4",
            "decision_id": "decision-q4",
            "provider_plugin_id": "gpt-4-o",
            "system_prompt": "SYSTEM_Q4",
            "prompt": "PROMPT_Q4",
            "context": {
                "q1_scene_model": state.current_context["q1_scene_model"],
                "q1_uncertainty_profile": state.current_context["q1_uncertainty_profile"],
                "q2_role_profile": state.current_context["q2_role_profile"],
                "q2_mission_boundary": state.current_context["q2_mission_boundary"],
                "q3_unified_asset_inventory": state.current_context["q3_unified_asset_inventory"],
                "q3_resource_evaluation": state.current_context["q3_resource_evaluation"],
            },
            "caller_context": {
                "source_module": "q4_what_can_i_do_plugin",
                "invocation_phase": "nine_question_q4_what_can_i_do",
                "question_driver_refs": ["我能做什么"],
            },
        },
        source="test.q4.production",
        trace_id="trace-q4-production",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q4-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {"capability_boundary_profile": state.current_context["q4_capability_boundary_profile"]},
            "raw_response": {"id": "raw-q4", "capability_boundary_profile": state.current_context["q4_capability_boundary_profile"]},
            "token_usage": {"input_tokens": 101, "output_tokens": 44, "total_tokens": 145},
            "model": "gpt-4-o",
            "elapsed_ms": 360,
        },
        source="test.q4.production",
        trace_id="trace-q4-production",
    )

    registry = CognitiveToolRegistry(transcript_store=BrainTranscriptStore(tmp_path / "registry_transcript.jsonl"))
    q4_plugin = build_q4_what_can_i_do_plugin()
    registry.register(q4_plugin, description="q4 sandbox")
    registry.promote_plugin(q4_plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "test promote")
    registry.promote_plugin(q4_plugin.plugin_id, PluginLifecycleStatus.ACTIVE, "test activate")

    app = create_web_console_app(
        cognitive_tool_registry=registry,
        runtime=runtime,
        session=session,
        managed_plugins=[build_managed_plugin_record(provider)],
    )
    return TestClient(app), runtime


def test_q4_detail_endpoint_returns_full_evidence_and_capability_profile(tmp_path: Path) -> None:
    provider = StaticQ4Provider(
        plugin_id="static-q4-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["static-q4-regression"],
        revocation_reasons=[],
        provider_name="static-q4",
        api_base="https://provider.invalid",
        api_key_env="INLINE_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client, _ = _build_q4_runtime_client(provider, tmp_path)

    response = client.get("/api/web/nine-questions/q4")
    assert response.status_code == 200
    payload = response.json()
    assert payload["question_id"] == "q4"
    assert payload["preprocessed_evidence"]["q1_context"]["scene_model"]["primary_domain"] == "audit_console"
    assert payload["preprocessed_evidence"]["q2_context"]["role_profile"]["active_role"] == "auditor"
    assert payload["preprocessed_evidence"]["q3_inventory"]["available_cognitive_tools"] == ["MemorySearch", "CodeAnalyzer"]
    assert payload["inference_result"]["actionable_space"] == ["view_dashboard", "inspect_audit_log"]
    assert payload["llm_trace_payload"]["source_module"] == "q4_what_can_i_do_plugin"
    assert payload["llm_trace_payload"]["question_driver_refs"] == ["我能做什么"]
    assert payload["llm_trace_payload"]["raw_response"]["id"] == "raw-q4"


def test_q4_sandbox_fail_closed_and_no_production_pollution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_Q4_BAD_KEY", "bad-key")
    provider = AuthFailingQ4Provider(
        plugin_id="auth-fail-q4-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["auth-failure"],
        revocation_reasons=[],
        provider_name="auth-fail-q4",
        api_base="https://provider.invalid",
        api_key_env="TEST_Q4_BAD_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client, runtime = _build_q4_runtime_client(provider, tmp_path)
    before_snapshot = dict(runtime.nine_question_state.question_snapshots)
    before_entries = runtime.transcript_store.search_entries()
    before_hash = _file_sha256(runtime.transcript_store.file_path)

    response = client.post(
        "/api/web/nine-questions/q4/test",
        json={
            "mock_context": {
                "q3_unified_asset_inventory": {
                    "available_cognitive_tools": ["MemorySearch"],
                    "available_execution_tools": [],
                    "connected_agents": [],
                    "activated_strategy_patches": ["Patch-v3: disallow write path"],
                    "accessible_workspace_zones": ["/workspace/audit"],
                    "permissions": {"mode": "read_only"},
                }
            }
        },
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"]["error_code"] == "llm_auth_error"
    assert "认证失败" in payload["detail"]["user_message"]
    assert runtime.nine_question_state.question_snapshots == before_snapshot
    assert runtime.transcript_store.search_entries() == before_entries
    assert _file_sha256(runtime.transcript_store.file_path) == before_hash
