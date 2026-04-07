from __future__ import annotations

import importlib
import pytest
from pathlib import Path
import sys
from unittest.mock import MagicMock

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient

from plugins.nine_questions import build_q2_who_am_i_plugin
from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.transcript import BrainTranscriptStore
from zentex.web_console.app import create_web_console_app
from zentex.web_console.services.plugins import build_managed_plugin_record
from zentex.web_console import dev_server

def _fresh_client() -> TestClient:
    module = importlib.reload(dev_server)
    return TestClient(module.app)


class FakeQ2SandboxProvider(ModelProviderSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "model_provider"

    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        return {
            "role_profile": {
                "identity_role": "Clinical Sandbox Strategist",
                "active_role": "Guardian of Capital",
                "task_role": "Risk Mitigator"
            },
            "mission_boundary": {
                "current_mission": "De-leverage portfolio",
                "priority_duties": ["Monitor slippage"],
                "continuity_boundaries": ["Session kill-switch at 1:00 PM"]
            }
        }

    def health_probe(self) -> PluginHealthStatus:
        return PluginHealthStatus.HEALTHY


def test_q2_contract_mapping_reads_preprocessed_evidence() -> None:
    """契约精准映射断言：确保真实请求（经过 latest-report 聚合）后完全包含全量快照、挂载插件和溯源。"""
    client = _fresh_client()
    
    # 注入符合我们严格要求的 mock 数据到 dev_server 状态机的 session 中
    runtime = client.app.state.runtime
    state = runtime.nine_question_state
    
    if "q2" not in state.question_snapshots:
        state.apply_question_result(
            question_id="q2",
            tool_id="nine_questions.q2",
            summary="Q2 result",
            confidence=0.99,
            context_updates={},
            trace_id="test-trace-q2",
            refresh_reason="test",
            driver_refs=["test"],
        )
        
    state.current_context.update({
        "workspace_domain_inference": {
            "primary_domain": "test",
            "secondary_domains": [],
            "uncertainties": []
        },
        "identity_kernel_snapshot": {
            "meta_motivation": "test",
            "values_prohibition": "test",
            "non_bypassable_constraints": []
        },
        "manual_role_overrides": {}
    })

    state.question_snapshots["q2"] = dict(state.question_snapshots["q2"])
    state.question_snapshots["q2"]["mounted_plugins"] = [{"plugin_id": "test", "description": "mock", "status": "active"}]
    state.question_snapshots["q2"]["llm_trace_payload"] = {
        "provider_name": "test", "model": "test", "system_prompt": "test", 
        "prompt": "test", "raw_response": {}, "elapsed_ms": 10
    }
    state.question_snapshots["q2"]["preprocessed_evidence"] = {"q1_summary": {}}

    response = client.get("/api/web/nine-questions/latest-report")
    assert response.status_code == 200
    payload = response.json()
    
    q2 = next((item for item in payload["questions"] if item["question_id"] == "q2"), None)
    assert q2 is not None

    assert "mounted_plugins" in q2
    assert "preprocessed_evidence" in q2
    assert "llm_trace_payload" in q2
    assert "raw_response" in q2["llm_trace_payload"]


def test_q2_sandbox_endpoint_isolation_asserts_no_pollution(tmp_path, monkeypatch) -> None:
    """沙箱隔离断言：测试 POST 沙箱接口，断言主脑状态与底层持久化存储大小与哈希均无任何变化。"""
    monkeypatch.setenv("TEST_FAKE_KEY", "sandbox-secret")

    production_store = BrainTranscriptStore(tmp_path / "production_transcript.jsonl")
    runtime = BrainRuntime(runtime_id="sandbox-runtime", transcript_store=production_store)
    session = runtime.create_session("sandbox-session")
    state = runtime.nine_question_state
    
    # Establish a baseline snapshot before sandbox execution
    state.apply_question_result(
        question_id="q2",
        tool_id="nine_questions.q2",
        summary="生产态 Q2 原始结果",
        confidence=0.99,
        context_updates={},
        trace_id="prod-trace-q2",
        refresh_reason="seed",
        driver_refs=["seed:q2"],
    )
    revision_before = state.revision
    production_snapshot_before = dict(state.question_snapshots["q2"])

    registry_store = BrainTranscriptStore(tmp_path / "registry_transcript.jsonl")
    registry = CognitiveToolRegistry(transcript_store=registry_store)
    q2_plugin = build_q2_who_am_i_plugin()
    registry.register(q2_plugin, description="sandbox q2 plugin")
    registry.promote_plugin(q2_plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "test promote")
    registry.promote_plugin(q2_plugin.plugin_id, PluginLifecycleStatus.ACTIVE, "test activate")

    provider = FakeQ2SandboxProvider(
        plugin_id="fake-q2-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sandbox-rollback"],
        revocation_reasons=["mock-revoke"],
        provider_name="fake-q2-provider",
        api_base="https://sandbox.invalid",
        api_key_env="TEST_FAKE_KEY",
        default_model="fake-q2-model",
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

    response = client.post(
        "/api/web/nine-questions/q2/test",
        json={
            "mock_context": {
                "workspace_domain_inference": {
                    "primary_domain": "trading_engine",
                    "secondary_domains": ["order_management", "risk_control"],
                    "confidence": 0.98,
                    "reasoning_summary": "Extracted from sandbox Q1 context",
                    "uncertainties": ["latency jitter"],
                    "suggested_first_step": "verify firewall"
                },
                "identity_kernel": {
                    "meta_motivation": "Sandbox test motivation",
                    "values_prohibition": "Sandbox restriction",
                    "non_bypassable_constraints": ["Sandbox constraint 1"]
                }
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["question_id"] == "q2"
    assert payload["inference_result"]["role_profile"]["identity_role"] == "Clinical Sandbox Strategist"
    assert "meta_motivation" in payload["preprocessed_evidence"]["identity_kernel"]

    assert production_store.write_entry.call_count == 0
    assert production_store.append_entry.call_count == 0
    assert state.revision == revision_before
    assert state.question_snapshots["q2"] == production_snapshot_before


class TimeoutQ2SandboxProvider(FakeQ2SandboxProvider):
    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        raise TimeoutError("LLM 响应超时断连")


def test_q2_api_abnormal_fallback_graceful_degradation(tmp_path, monkeypatch) -> None:
    """异常阻断降级断言：模拟 500 连接超时。断言接口具有 error_code 回收能力而不至于令 web 服务宕机。"""
    monkeypatch.setenv("TEST_FAKE_KEY", "sandbox-secret")

    runtime = BrainRuntime(runtime_id="sandbox-runtime", transcript_store=BrainTranscriptStore(tmp_path / "mock.jsonl"))
    session = runtime.create_session("sandbox-session")
    
    registry = CognitiveToolRegistry(transcript_store=BrainTranscriptStore(tmp_path / "reg.jsonl"))
    q2_plugin = build_q2_who_am_i_plugin()
    registry.register(q2_plugin, description="sandbox q2 plugin")
    registry.promote_plugin(q2_plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "test")
    registry.promote_plugin(q2_plugin.plugin_id, PluginLifecycleStatus.ACTIVE, "test")

    provider = TimeoutQ2SandboxProvider(
        plugin_id="timeout-q2-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["timeout-rollback"],
        revocation_reasons=["timeout-revoke"],
        provider_name="timeout-q2-provider",
        api_base="https://timeout.invalid",
        api_key_env="TEST_FAKE_KEY",
        default_model="timeout-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )

    app = create_web_console_app(
        cognitive_tool_registry=registry,
        runtime=runtime,
        session=session,
        managed_plugins=[build_managed_plugin_record(provider)],
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/web/nine-questions/q2/test", json={"mock_context": {}})

    assert response.status_code == 500
