from __future__ import annotations

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

from plugins.nine_questions.q5_what_am_i_allowed_to_do.q5_what_am_i_allowed_to_do_plugin import (  # noqa: E402
    build_q5_what_am_i_allowed_to_do_plugin,
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


class StaticQ5Provider(ModelProviderSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "model_provider"

    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        return {
            "authorization_boundary_profile": {
                "execution_tier": "read_only",
                "allowed_action_space": ["read_workspace_state", "inspect_audit_log"],
                "forbidden_action_space": [
                    {"action": "delete_global_logs", "reason": "read_only tenant"},
                    {"action": "outbound_request_help", "reason": "contact policy forbids outbound"},
                ],
                "contact_and_org_boundaries": {
                    "interaction_scope": "tenant_internal_only",
                    "requires_human_confirmation": True,
                    "requires_cloud_audit": False,
                    "allowed_delegation_targets": ["human_operator", "trusted_agent_alpha"],
                },
                "requires_escalation_actions": ["delegate_to_human"],
            }
        }

    def health_probe(self) -> PluginHealthStatus:
        return PluginHealthStatus.HEALTHY


class AuthFailingQ5Provider(StaticQ5Provider):
    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        raise ModelProviderAuthError("provider rejected supplied API key")


def _build_q5_runtime_client(provider: ModelProviderSpec, tmp_path: Path) -> tuple[TestClient, BrainRuntime]:
    production_transcript = BrainTranscriptStore(tmp_path / "production_transcript.jsonl")
    runtime = BrainRuntime(runtime_id="q5-runtime", transcript_store=production_transcript)
    session = runtime.create_session("q5-session")
    state = session.current_nine_question_state

    q5_profile = {
        "execution_tier": "read_only",
        "forbidden_action_space": [
            {"action": "delete_global_logs", "reason": "read_only tenant"},
            {"action": "outbound_request_help", "reason": "contact policy forbids outbound"},
        ],
        "contact_and_org_boundaries": {
            "interaction_scope": "tenant_internal_only",
            "requires_human_confirmation": True,
            "requires_cloud_audit": False,
            "allowed_delegation_targets": ["human_operator", "trusted_agent_alpha"],
        },
        "requires_escalation_actions": ["delegate_to_human"],
    }
    state.current_context.update(
        {
            "q4_capability_boundary_profile": {
                "actionable_space": ["read_workspace_state", "inspect_audit_log", "delete_global_logs"],
            },
            "contact_policy": {
                "allow_outbound": False,
                "allow_inbound": True,
                "whitelist": ["trusted_agent_alpha"],
            },
            "tenant_scope": {
                "tenant_scope": "tenant_alpha",
                "mode": "read_only",
                "secrecy_level": "restricted",
            },
            "q3_connected_agents": [
                {"agent_id": "trusted_agent_alpha", "trust_level": "trusted", "scope": "read_only"},
                {"agent_id": "agent_pending_beta", "trust_level": "pending", "scope": "read_only"},
            ],
            "q5_authorization_boundary_profile": q5_profile,
        }
    )
    state.apply_question_result(
        question_id="q5",
        tool_id="nine_questions.q5",
        summary="execution_tier=read_only; forbidden=2",
        confidence=0.89,
        context_updates={"q5_authorization_boundary_profile": q5_profile},
        trace_id="trace-q5-production",
        refresh_reason="unit_test",
        driver_refs=["我被允许做什么"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q5-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q5",
            "decision_id": "decision-q5",
            "provider_plugin_id": "gpt-4-o",
            "system_prompt": "SYSTEM_Q5",
            "prompt": "PROMPT_Q5",
            "context": {
                "q4_capability_boundary_profile": state.current_context["q4_capability_boundary_profile"],
                "contact_policy": state.current_context["contact_policy"],
                "tenant_scope": state.current_context["tenant_scope"],
                "q3_connected_agents": state.current_context["q3_connected_agents"],
            },
            "caller_context": {
                "source_module": "q5_what_am_i_allowed_to_do_plugin",
                "invocation_phase": "nine_question_q5_authorization",
                "question_driver_refs": ["我被允许做什么"],
            },
        },
        source="test.q5.production",
        trace_id="trace-q5-production",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q5-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {"authorization_boundary_profile": q5_profile},
            "raw_response": {"id": "raw-q5", "authorization_boundary_profile": q5_profile},
            "token_usage": {"input_tokens": 133, "output_tokens": 57, "total_tokens": 190},
            "model": "gpt-4-o",
            "elapsed_ms": 410,
        },
        source="test.q5.production",
        trace_id="trace-q5-production",
    )

    registry = CognitiveToolRegistry(transcript_store=BrainTranscriptStore(tmp_path / "registry_transcript.jsonl"))
    q5_plugin = build_q5_what_am_i_allowed_to_do_plugin()
    registry.register(q5_plugin, description="q5 sandbox")
    registry.promote_plugin(q5_plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "test promote")
    registry.promote_plugin(q5_plugin.plugin_id, PluginLifecycleStatus.ACTIVE, "test activate")

    app = create_web_console_app(
        cognitive_tool_registry=registry,
        runtime=runtime,
        session=session,
        managed_plugins=[build_managed_plugin_record(provider)],
    )
    return TestClient(app), runtime


def test_q5_latest_report_exposes_compliance_evidence_and_trace(tmp_path: Path) -> None:
    provider = StaticQ5Provider(
        plugin_id="static-q5-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["static-q5-regression"],
        revocation_reasons=[],
        provider_name="static-q5",
        api_base="https://provider.invalid",
        api_key_env="INLINE_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client, _ = _build_q5_runtime_client(provider, tmp_path)

    response = client.get("/api/web/nine-questions/latest-report")
    assert response.status_code == 200
    payload = response.json()
    q5 = next(item for item in payload["questions"] if item["question_id"] == "q5")
    assert q5["preprocessed_evidence"]["actionable_space"] == [
        "read_workspace_state",
        "inspect_audit_log",
        "delete_global_logs",
    ]
    assert "allow_outbound=false" in q5["preprocessed_evidence"]["contact_policy"]
    assert "mode=read_only" in q5["preprocessed_evidence"]["tenant_boundaries"]
    assert q5["preprocessed_evidence"]["agent_trust_status"]["agent_pending_beta"] == "pending"
    assert q5["inference_result"]["execution_tier"] == "read_only"
    assert "delete_global_logs: read_only tenant" in q5["inference_result"]["explicitly_forbidden_actions"]
    assert "contact policy forbids outbound" in q5["inference_result"]["compliance_risks"]
    assert q5["inference_result"]["allowed_delegation_targets"] == ["human_operator", "trusted_agent_alpha"]
    assert q5["llm_trace_payload"]["raw_response"]["id"] == "raw-q5"


def test_q5_sandbox_fail_closed_and_no_production_pollution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_Q5_BAD_KEY", "bad-key")
    provider = AuthFailingQ5Provider(
        plugin_id="auth-fail-q5-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["auth-failure"],
        revocation_reasons=[],
        provider_name="auth-fail-q5",
        api_base="https://provider.invalid",
        api_key_env="TEST_Q5_BAD_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client, runtime = _build_q5_runtime_client(provider, tmp_path)
    before_snapshot = dict(runtime.nine_question_state.question_snapshots)
    before_entries = runtime.transcript_store.search_entries()

    response = client.post(
        "/api/web/nine-questions/q5/test",
        json={
            "mock_context": {
                "q4_capability_boundary_profile": {
                    "actionable_space": ["read_workspace_state", "delete_global_logs"],
                },
                "contact_policy": {"allow_outbound": False},
                "tenant_scope": {"mode": "read_only"},
                "q3_connected_agents": [{"agent_id": "agent_pending_beta", "trust_level": "pending"}],
            }
        },
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"]["error_code"] == "llm_auth_error"
    assert "认证失败" in payload["detail"]["user_message"]
    assert runtime.nine_question_state.question_snapshots == before_snapshot
    assert runtime.transcript_store.search_entries() == before_entries
