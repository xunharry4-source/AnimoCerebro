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

from plugins.nine_questions.q3_what_do_i_have.q3_what_do_i_have_plugin import (  # noqa: E402
    build_q3_what_do_i_have_plugin,
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


class StaticQ3Provider(ModelProviderSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "model_provider"

    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        return {
            "unified_asset_inventory": {
                "available_cognitive_tools": ["CodeAnalyzer", "MemorySearch"],
                "available_execution_tools": ["ShellExecutor", "GrepSearch"],
                "connected_agents": [
                    {"id": "agent-1", "name": "SecurityAgent", "summary": "External security scanner", "status": "online"},
                    {"id": "agent-2", "name": "OfflineAgent", "summary": "Should be filtered", "status": "offline"},
                ],
                "activated_strategy_patches": ["Patch-v2.1: Disallow direct root access"],
                "accessible_workspace_zones": ["/workspaces/project-alpha", "/workspaces/audit-log"],
            },
            "resource_evaluation": {
                "resource_status": "critically_lacking",
                "missing_critical_assets": ["GPU_CLUSTER_ACCESS", "WRITE_PERM_ETC"],
                "bottleneck_node": "Auth-Gateway-Node-B",
            },
        }

    def health_probe(self) -> PluginHealthStatus:
        return PluginHealthStatus.HEALTHY


class AuthFailingQ3Provider(StaticQ3Provider):
    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        raise ModelProviderAuthError("provider rejected supplied API key")


def _build_q3_runtime_client(provider: ModelProviderSpec, tmp_path: Path) -> tuple[TestClient, BrainRuntime]:
    production_transcript = BrainTranscriptStore(tmp_path / "production_transcript.jsonl")
    runtime = BrainRuntime(runtime_id="q3-runtime", transcript_store=production_transcript)
    session = runtime.create_session("q3-session")
    state = session.current_nine_question_state
    state.current_context.update(
        {
            "q3_unified_asset_inventory": {
                "available_cognitive_tools": ["CodeAnalyzer", "MemorySearch"],
                "available_execution_tools": ["ShellExecutor", "GrepSearch"],
                "connected_agents": [
                    {"id": "agent-1", "name": "SecurityAgent", "summary": "External security scanner", "status": "online"},
                    {"id": "agent-2", "name": "OfflineAgent", "summary": "Should be filtered", "status": "offline"},
                ],
                "activated_strategy_patches": ["Patch-v2.1: Disallow direct root access"],
                "accessible_workspace_zones": ["/workspaces/project-alpha", "/workspaces/audit-log"],
            },
            "permissions": {
                "tenant_scope": ["TENANT_ALPHA", "READ_CODE"],
                "brain_scope": ["EXECUTE_TOOL"],
                "accessible_workspace_zones": ["/workspaces/project-alpha", "/workspaces/audit-log"],
            },
            "active_tools": {
                "available_cognitive_tools": ["CodeAnalyzer", "MemorySearch"],
                "available_execution_tools": ["ShellExecutor", "GrepSearch"],
            },
            "loaded_memories": {
                "experience_logs": ["Experience 1"],
                "activated_strategy_patches": ["Patch-v2.1: Disallow direct root access"],
            },
            "q3_resource_evaluation": {
                "resource_status": "critically_lacking",
                "missing_critical_assets": ["GPU_CLUSTER_ACCESS", "WRITE_PERM_ETC"],
                "bottleneck_node": "Auth-Gateway-Node-B",
                "reasoning_summary": "Gateway blocked.",
            },
            "q3_humanized_asset_inventory": {
                "cognitive_tool_rows": [
                    {
                        "id": "CodeAnalyzer",
                        "name": "Code Analyzer",
                        "introduction": "Code Analyzer 是当前可用的认知工具。",
                        "function_description": "用于理解代码结构与风险线索。",
                    },
                    {
                        "id": "MemorySearch",
                        "name": "Memory Search",
                        "introduction": "Memory Search 是当前可用的认知工具。",
                        "function_description": "用于检索经验和历史策略记录。",
                    },
                ],
                "execution_tool_rows": [
                    {
                        "id": "ShellExecutor",
                        "name": "Shell Executor",
                        "introduction": "Shell Executor 是当前可用的执行工具。",
                        "function_description": "用于执行受控命令和本地系统操作。",
                    },
                    {
                        "id": "GrepSearch",
                        "name": "Grep Search",
                        "introduction": "Grep Search 是当前可用的执行工具。",
                        "function_description": "用于在工作区中快速检索文本线索。",
                    },
                ],
                "connected_agent_rows": [
                    {
                        "id": "agent-1",
                        "name": "SecurityAgent",
                        "introduction": "SecurityAgent 是当前在线协作 Agent。",
                        "function_description": "用于执行安全审计与风险检查。",
                        "status": "online",
                    }
                ],
            },
        }
    )
    state.apply_question_result(
        question_id="q3",
        tool_id="nine_questions.q3",
        summary="resource_status=critically_lacking; bottleneck=Auth-Gateway-Node-B",
        confidence=0.84,
        context_updates={
            "q3_unified_asset_inventory": state.current_context["q3_unified_asset_inventory"],
            "q3_resource_evaluation": state.current_context["q3_resource_evaluation"],
        },
        trace_id="trace-q3-production",
        refresh_reason="unit_test",
        driver_refs=["我有什么"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q3-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q3",
            "decision_id": "decision-q3",
            "provider_plugin_id": "gpt-4-o",
            "system_prompt": "SYSTEM_Q3",
            "prompt": "PROMPT_Q3",
            "context": {
                "q3_unified_asset_inventory": state.current_context["q3_unified_asset_inventory"],
                "q3_humanized_asset_inventory": state.current_context["q3_humanized_asset_inventory"],
                "permissions": state.current_context["permissions"],
                "active_tools": state.current_context["active_tools"],
                "loaded_memories": state.current_context["loaded_memories"],
            },
            "caller_context": {
                "source_module": "q3_what_do_i_have_plugin",
                "invocation_phase": "nine_question_q3_what_do_i_have",
                "question_driver_refs": ["我有什么"],
            },
        },
        source="test.q3.production",
        trace_id="trace-q3-production",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q3-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {
                "q3_unified_asset_inventory": state.current_context["q3_unified_asset_inventory"],
                "q3_resource_evaluation": state.current_context["q3_resource_evaluation"],
                "resource_evaluation": state.current_context["q3_resource_evaluation"],
            },
            "raw_response": {"id": "raw-q3", "resource_evaluation": {"resource_status": "critically_lacking"}},
            "token_usage": {"input_tokens": 120, "output_tokens": 35, "total_tokens": 155},
            "model": "gpt-4-o",
            "elapsed_ms": 420,
        },
        source="test.q3.production",
        trace_id="trace-q3-production",
    )

    registry = CognitiveToolRegistry(transcript_store=BrainTranscriptStore(tmp_path / "registry_transcript.jsonl"))
    q3_plugin = build_q3_what_do_i_have_plugin()
    registry.register(q3_plugin, description="q3 sandbox")
    registry.promote_plugin(q3_plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "test promote")
    registry.promote_plugin(q3_plugin.plugin_id, PluginLifecycleStatus.ACTIVE, "test activate")

    app = create_web_console_app(
        cognitive_tool_registry=registry,
        runtime=runtime,
        session=session,
        managed_plugins=[build_managed_plugin_record(provider)],
    )
    return TestClient(app), runtime


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_q3_detail_endpoint_filters_offline_agents_and_exposes_trace_payload(tmp_path: Path) -> None:
    provider = StaticQ3Provider(
        plugin_id="static-q3-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["static-q3-regression"],
        revocation_reasons=[],
        provider_name="static-q3",
        api_base="https://provider.invalid",
        api_key_env="INLINE_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client, _ = _build_q3_runtime_client(provider, tmp_path)

    response = client.get("/api/web/nine-questions/q3")
    assert response.status_code == 200
    payload = response.json()
    assert payload["question_id"] == "q3"
    assert payload["preprocessed_evidence"]["tools_agents"]["connected_agents"] == [
        {"id": "agent-1", "name": "SecurityAgent", "summary": "External security scanner", "status": "online"}
    ]
    assert payload["preprocessed_evidence"]["tools_agents"]["cognitive_tool_rows"][0]["name"] == "Code Analyzer"
    assert payload["preprocessed_evidence"]["tools_agents"]["execution_tool_rows"][0]["function_description"] == "用于执行受控命令和本地系统操作。"
    assert payload["preprocessed_evidence"]["tools_agents"]["connected_agent_rows"][0]["name"] == "SecurityAgent"
    assert payload["inference_result"]["sufficiency_assessment"]["resource_status"] == "critically_lacking"
    assert payload["inference_result"]["sufficiency_assessment"]["resource_status_label"] == "关键资源匮乏"
    assert payload["llm_trace_payload"]["raw_response"]["id"] == "raw-q3"
    assert payload["llm_trace_payload"]["source_module"] == "q3_what_do_i_have_plugin"
    assert payload["llm_trace_payload"]["question_driver_refs"] == ["我有什么"]


def test_q3_sandbox_fail_closed_and_no_production_pollution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_Q3_BAD_KEY", "bad-key")
    provider = AuthFailingQ3Provider(
        plugin_id="auth-fail-q3-provider",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["auth-failure"],
        revocation_reasons=[],
        provider_name="auth-fail-q3",
        api_base="https://provider.invalid",
        api_key_env="TEST_Q3_BAD_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client, runtime = _build_q3_runtime_client(provider, tmp_path)
    before_snapshot = dict(runtime.nine_question_state.question_snapshots)
    before_entries = runtime.transcript_store.search_entries()
    before_hash = _file_sha256(runtime.transcript_store.file_path)

    response = client.post(
        "/api/web/nine-questions/q3/test",
        json={
            "mock_context": {
                "active_tools": {"available_cognitive_tools": ["CodeAnalyzer"], "available_execution_tools": []},
                "permissions": {"tenant_scope": ["READ_CODE"], "brain_scope": []},
                "connected_agents": [{"id": "offline-1", "status": "offline"}],
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
