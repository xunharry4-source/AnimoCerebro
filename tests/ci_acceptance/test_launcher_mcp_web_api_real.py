from __future__ import annotations

import os
import tempfile
from uuid import uuid4

import requests
from fastapi import FastAPI, Request

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.agents.auth import AgentAuthService
from zentex.launcher.assembly.assembler import SystemAssembler
from zentex.launcher.config.startup_config import StartupConfig
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.http_transport import HttpJsonMcpTransportClient
from zentex.mcp.service import McpIntegrationService
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry, ExecutionDomainRegistry
from zentex.web_console.routers import mcp as mcp_router


class _TranscriptStore:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def write_entry(self, **payload) -> None:
        self.entries.append(payload)


def _mcp_api_app(mcp_service: object) -> FastAPI:
    app = FastAPI()
    app.state.mcp_service = mcp_service
    app.include_router(mcp_router.router, prefix="/api/web")
    return app


def _registered_mcp_service(registry_path: str) -> McpIntegrationService:
    transcript_store = _TranscriptStore()
    adapter = McpAdapterPlugin(
        plugin_id="mcp-real-http-adapter",
        version="1.0.0",
        feature_code="real.mcp",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["mcp_regression"],
        revocation_reasons=["mcp_disabled"],
        server_configs=[],
    )
    adapter.attach_runtime(
        client_factory=lambda _config: HttpJsonMcpTransportClient(timeout_seconds=2.0),
        transcript_store=transcript_store,
        cognitive_registry=CognitiveToolRegistry(transcript_store=transcript_store),
        execution_registry=ExecutionDomainRegistry(),
        auth_service=AgentAuthService(),
    )
    return McpIntegrationService(
        adapter=adapter,
        auth_service=AgentAuthService(),
        registry_path=registry_path,
    )


def _real_http_mcp_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/tools")
    def tools() -> dict:
        return {
            "tools": [
                {
                    "tool_name": "echo",
                    "description": "Echo arguments through a real HTTP MCP-compatible endpoint.",
                    "input_schema": {"type": "object"},
                    "mutates_state": False,
                    "read_only_hint": True,
                }
            ]
        }

    @app.post("/tools/echo/call")
    async def call(request: Request) -> dict:
        payload = await request.json()
        return {"accepted": True, "arguments": payload.get("arguments", {})}

    return app


def test_launcher_assembled_mcp_service_does_not_seed_unregistered_servers() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        previous_root = os.environ.get("ZENTEX_DATA_ROOT")
        os.environ["ZENTEX_DATA_ROOT"] = tmpdir
        try:
            assembly = SystemAssembler(StartupConfig()).assemble()
        finally:
            if previous_root is None:
                os.environ.pop("ZENTEX_DATA_ROOT", None)
            else:
                os.environ["ZENTEX_DATA_ROOT"] = previous_root

        mcp_service = assembly.registry.get("mcp")
        assert "mcp" not in assembly.errors
        assert mcp_service is not None
        assert getattr(mcp_service, "_is_stub", False) is False

        with live_http_server(_mcp_api_app(mcp_service)) as base_url:
            response = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
            assert response.status_code == 200, response.text
            payload = response.json()

        assert isinstance(payload, list)
        server_ids = {item.get("server_id") for item in payload}
        assert "knowledge-hub" not in server_ids
        assert "ops-bridge" not in server_ids


def test_mcp_web_api_registers_real_http_server_and_query_returns_registered_record() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _registered_mcp_service(f"{tmpdir}/mcp_registry.json")
        server_id = f"real-http-mcp-{uuid4().hex[:8]}"

        with live_http_server(_real_http_mcp_app()) as mcp_base_url:
            with live_http_server(_mcp_api_app(service)) as api_base_url:
                create_response = requests.post(
                    f"{api_base_url}/api/web/mcp-servers/register",
                    json={
                        "server_id": server_id,
                        "transport_type": "http",
                        "command": mcp_base_url,
                        "tool_bindings": [{"tool_name": "echo", "domain": "cognitive"}],
                        "documentation_learning_required": False,
                    },
                    timeout=10,
                )
                assert create_response.status_code == 200, create_response.text
                created = create_response.json()
                assert created["server_id"] == server_id
                assert created["transport_type"] == "http"
                assert created["status"] == "online"
                assert created["tool_count"] == 1
                assert created["tools"][0]["tool_name"] == "echo"
                assert created["tools"][0]["mcp_id"] == f"mcp:{server_id}:echo"

                list_response = requests.get(f"{api_base_url}/api/web/mcp-servers", timeout=10)
                assert list_response.status_code == 200, list_response.text
                records = list_response.json()

            restored_service = _registered_mcp_service(f"{tmpdir}/mcp_registry.json")
            with live_http_server(_mcp_api_app(restored_service)) as restored_api_base_url:
                restored_response = requests.get(f"{restored_api_base_url}/api/web/mcp-servers", timeout=10)
                assert restored_response.status_code == 200, restored_response.text
                restored_records = restored_response.json()

        by_id = {item["server_id"]: item for item in records}
        assert server_id in by_id
        record = by_id[server_id]
        assert record["status"] == "online"
        assert record["tool_count"] == 1
        assert record["tools"][0]["feature_code"] == f"mcp.{server_id}.echo"

        restored_by_id = {item["server_id"]: item for item in restored_records}
        assert server_id in restored_by_id
        restored = restored_by_id[server_id]
        assert restored["status"] == "online"
        assert restored["tool_count"] == 1
        assert restored["tools"][0]["tool_name"] == "echo"
