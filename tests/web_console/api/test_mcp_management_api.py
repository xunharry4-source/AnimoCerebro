from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from zentex.core.execution_registry import ExecutionDomainRegistry
from zentex.core.mcp import McpToolDescriptor
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.mcp.adapter import FakeMcpTransportClient, McpAdapterPlugin
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.transcript import BrainTranscriptStore
from zentex.web_console.app import create_web_console_app


def _build_client(tmp_path: Path) -> TestClient:
    transcript_store = BrainTranscriptStore(tmp_path / "mcp-api-transcript.jsonl")
    runtime = BrainRuntime(runtime_id="mcp-api-runtime", transcript_store=transcript_store)
    session = runtime.create_session("mcp-api-session")
    cognitive_registry = CognitiveToolRegistry(transcript_store=transcript_store)
    execution_registry = ExecutionDomainRegistry()
    transports = {
        "knowledge-hub": FakeMcpTransportClient(
            tools=[
                McpToolDescriptor(
                    tool_name="search_documents",
                    description="Search indexed notes",
                    input_schema={"type": "object"},
                    mutates_state=False,
                    read_only_hint=True,
                )
            ],
            invocations={
                "search_documents": {
                    "summary": "search completed",
                    "hits": ["runbook-42"],
                }
            },
        )
    }
    adapter = McpAdapterPlugin(
        plugin_id="mcp-adapter-test",
        version="1.0.0",
        feature_code="external.mcp",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["mcp_adapter_regression"],
        revocation_reasons=["mcp_adapter_disabled"],
        health_probe_endpoint="mcp://health",
        server_configs=[],
    )
    adapter.attach_runtime(
        client_factory=lambda config: transports[config.server_id],
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    app = create_web_console_app(
        runtime=runtime,
        session=session,
        cognitive_tool_registry=cognitive_registry,
        execution_registry=execution_registry,
        mcp_adapter=adapter,
    )
    return TestClient(app)


def test_mcp_server_registration_and_listing(tmp_path: Path) -> None:
    client = _build_client(tmp_path)

    response = client.post(
        "/api/web/mcp-servers/register",
        json={
            "server_id": "knowledge-hub",
            "transport_type": "stdio",
            "command": "uvx",
            "args": ["knowledge-hub-mcp"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["server_id"] == "knowledge-hub"
    assert payload["status"] == "online"
    assert payload["tool_count"] == 1

    listing = client.get("/api/web/mcp-servers")
    assert listing.status_code == 200
    rows = listing.json()
    assert any(item["server_id"] == "knowledge-hub" for item in rows)


def test_mcp_server_test_call_uses_registered_transport(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    register = client.post(
        "/api/web/mcp-servers/register",
        json={
            "server_id": "knowledge-hub",
            "transport_type": "stdio",
            "command": "uvx",
            "args": ["knowledge-hub-mcp"],
        },
    )
    assert register.status_code == 200

    response = client.post(
        "/api/web/mcp-servers/knowledge-hub/test-call",
        json={"tool_name": "search_documents", "arguments": {"query": "runbook"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["server_id"] == "knowledge-hub"
    assert payload["tool_name"] == "search_documents"
    assert payload["payload"]["summary"] == "search completed"
    assert payload["payload"]["hits"] == ["runbook-42"]
