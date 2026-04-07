from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from zentex.cli.adapter import CliAdapterPlugin, SubprocessCliTransport
from zentex.core.execution_registry import ExecutionDomainRegistry
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.transcript import BrainTranscriptStore
from zentex.web_console.app import create_web_console_app


def _build_client(tmp_path: Path) -> TestClient:
    transcript_store = BrainTranscriptStore(tmp_path / "cli-api-transcript.jsonl")
    runtime = BrainRuntime(runtime_id="cli-api-runtime", transcript_store=transcript_store)
    session = runtime.create_session("cli-api-session")
    cognitive_registry = CognitiveToolRegistry(transcript_store=transcript_store)
    execution_registry = ExecutionDomainRegistry()
    cli_adapter = CliAdapterPlugin(
        plugin_id="cli-adapter-test",
        version="1.0.0",
        feature_code="external.cli",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["cli_adapter_regression"],
        revocation_reasons=["cli_adapter_disabled"],
    )
    cli_adapter.attach_runtime(
        transport=SubprocessCliTransport(),
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    app = create_web_console_app(
        runtime=runtime,
        session=session,
        cognitive_tool_registry=cognitive_registry,
        execution_registry=execution_registry,
        cli_adapter=cli_adapter,
    )
    return TestClient(app)


def test_cli_tool_registration_and_listing(tmp_path: Path) -> None:
    client = _build_client(tmp_path)

    response = client.post(
        "/api/web/cli-tools/register",
        json={
            "tool_name": "echo_probe",
            "command_executable": "/bin/echo",
            "description": "Read-only echo probe",
            "read_only_flag": True,
            "project_path": str(tmp_path),
            "project_name": "cli-api-test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["command_name"] == "echo_probe"
    assert payload["mapped_domain"] == "cognitive"

    listing = client.get("/api/web/cli-tools")
    assert listing.status_code == 200
    rows = listing.json()
    assert any(item["command_name"] == "echo_probe" for item in rows)


def test_cli_tool_test_call_runs_real_shell_command(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    register = client.post(
        "/api/web/cli-tools/register",
        json={
            "tool_name": "echo_probe",
            "command_executable": "/bin/echo",
            "description": "Read-only echo probe",
            "read_only_flag": True,
        },
    )
    assert register.status_code == 200

    response = client.post(
        "/api/web/cli-tools/echo_probe/test-call",
        json={"arguments": ["hello-zentex"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["exit_code"] == 0
    assert "hello-zentex" in payload["stdout"]
