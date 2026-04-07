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

from plugins.nine_questions import build_q1_where_am_i_plugin  # noqa: E402
from plugins.model_providers.provider_tools_provider import (  # noqa: E402
    build_default_provider_tools_model_provider,
)
from zentex.core.model_provider_spec import (  # noqa: E402
    ModelProviderAuthError,
    ModelProviderCallerContext,
    ModelProviderSpec,
    ModelProviderTimeoutError,
)
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus  # noqa: E402
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptStore  # noqa: E402
from zentex.web_console.app import create_web_console_app  # noqa: E402
from zentex.web_console.services.plugins import build_managed_plugin_record  # noqa: E402


class StaticModelProvider(ModelProviderSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "model_provider"

    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        return {
            "primary_domain": "sandbox_console",
            "secondary_domains": ["web_console"],
            "confidence": 0.91,
            "reasoning_summary": "static provider",
            "uncertainties": ["static provider test"],
            "suggested_first_step": "inspect sandbox output",
        }

    def health_probe(self) -> PluginHealthStatus:
        return PluginHealthStatus.HEALTHY


class AuthFailingModelProvider(StaticModelProvider):
    def generate_json(self, prompt: str, context: dict, caller_context: ModelProviderCallerContext, *, model=None) -> dict:
        raise ModelProviderAuthError("provider rejected supplied API key")


class ProbeAuthFailingModelProvider(StaticModelProvider):
    def health_probe(self) -> PluginHealthStatus:
        raise ModelProviderAuthError("health probe auth failed")


class ProbeTimeoutModelProvider(StaticModelProvider):
    def health_probe(self) -> PluginHealthStatus:
        raise ModelProviderTimeoutError("health probe timeout")


def _build_sandbox_client(provider: ModelProviderSpec, tmp_path: Path) -> TestClient:
    runtime = BrainRuntime(
        runtime_id="llm-fail-closed-runtime",
        transcript_store=BrainTranscriptStore(tmp_path / "production_transcript.jsonl"),
    )
    session = runtime.create_session("llm-fail-closed-session")
    runtime.nine_question_state.current_context.update(
        {
            "workspace_structure_analysis": {"directory_hierarchy_summary": "src/, tests/"},
            "workspace_content_samples": {"sampled_file_summaries": [{"path": "README.md", "summary": "sample"}]},
            "environment_event": {"kind": "manual_test"},
            "physical_host_state": {"memory_pressure": "low", "network_health": "healthy"},
        }
    )

    registry = CognitiveToolRegistry(transcript_store=BrainTranscriptStore(tmp_path / "registry_transcript.jsonl"))
    q1_plugin = build_q1_where_am_i_plugin()
    registry.register(q1_plugin, description="q1 sandbox")
    registry.promote_plugin(q1_plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "test promote")
    registry.promote_plugin(q1_plugin.plugin_id, PluginLifecycleStatus.ACTIVE, "test activate")

    app = create_web_console_app(
        cognitive_tool_registry=registry,
        runtime=runtime,
        session=session,
        managed_plugins=[build_managed_plugin_record(provider)],
    )
    return TestClient(app)


def test_q1_sandbox_returns_structured_error_when_api_key_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = build_default_provider_tools_model_provider(
        provider_name="openai",
        plugin_id="model-provider-openai",
    )
    monkeypatch.delenv(provider.api_key_env, raising=False)
    client = _build_sandbox_client(provider, tmp_path)

    response = client.post("/api/web/nine-questions/q1/test", json={"mock_context": {}})

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error_code"] == "llm_missing_credentials"
    assert "API Key" in payload["detail"]["user_message"]
    assert payload["detail"]["api_key_env"] == provider.api_key_env


def test_q1_sandbox_returns_structured_auth_error_when_provider_rejects_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_Q1_BAD_KEY", "bad-key")
    provider = AuthFailingModelProvider(
        plugin_id="model-provider-auth-failure",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["auth-failure"],
        revocation_reasons=["manual revoke"],
        provider_name="auth-failure-provider",
        api_base="https://provider.invalid",
        api_key_env="TEST_Q1_BAD_KEY",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client = _build_sandbox_client(provider, tmp_path)

    response = client.post("/api/web/nine-questions/q1/test", json={"mock_context": {}})

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"]["error_code"] == "llm_auth_error"
    assert "认证失败" in payload["detail"]["user_message"]
    assert payload["detail"]["provider_error_type"] == "ModelProviderAuthError"


def test_llm_status_probe_reports_auth_failure(tmp_path: Path) -> None:
    provider = ProbeAuthFailingModelProvider(
        plugin_id="model-provider-probe-auth-failure",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["auth-failure"],
        revocation_reasons=["manual revoke"],
        provider_name="probe-auth-provider",
        api_base="https://provider.invalid",
        api_key_env="inline-test-key",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client = _build_sandbox_client(provider, tmp_path)

    response = client.get("/api/web/llm/status?probe_live=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["probe_checked"] is True
    assert payload["reason"] == "auth_error"
    assert payload["provider_error_type"] == "ModelProviderAuthError"
    assert "认证失败" in payload["hint"]


def test_llm_status_probe_reports_timeout_failure(tmp_path: Path) -> None:
    provider = ProbeTimeoutModelProvider(
        plugin_id="model-provider-probe-timeout",
        version="1.0.0",
        feature_code="core.model_provider",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["timeout"],
        revocation_reasons=["manual revoke"],
        provider_name="probe-timeout-provider",
        api_base="https://provider.invalid",
        api_key_env="inline-test-key",
        default_model="fake-model",
        timeout_seconds=5.0,
        health_probe_endpoint="/health",
    )
    client = _build_sandbox_client(provider, tmp_path)

    response = client.get("/api/web/llm/status?probe_live=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["probe_checked"] is True
    assert payload["health_status"] == "unhealthy"
    assert payload["reason"] == "timeout"
    assert payload["provider_error_type"] == "ModelProviderTimeoutError"
