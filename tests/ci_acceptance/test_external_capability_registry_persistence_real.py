from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import zipfile
from uuid import uuid4

import requests
from fastapi import FastAPI, Request
from zentex.agents.manager import AgentStatus, AgentTrustLevel
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest
from zentex.cli.adapter import create_cli_adapter_plugin
from zentex.cli.models import CliToolRegistrationConfig
from zentex.cli.service import CliIntegrationService
from zentex.external_capabilities import ExternalCapabilityRegistryStore
from zentex.external_connectors.models import (
    ConnectorProfileLevel,
    ConnectorRegistrationRequest,
    ConnectorTestCallRequest,
    ConnectorType,
)
from zentex.external_connectors.service import ExternalConnectorService
from zentex.kernel import AuditEventStore
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.http_transport import HttpJsonMcpTransportClient
from zentex.mcp.models import McpServerConfig, McpToolBindingConfig
from zentex.mcp.service import McpIntegrationService
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry, ExecutionDomainRegistry
from zentex.web_console.routers import cli as cli_router
from zentex.web_console.routers import external_connectors as external_connectors_router
from zentex.web_console.routers import mcp as mcp_router
from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def _rows(db_path: str, table: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute(f"SELECT * FROM {table}"))
    finally:
        conn.close()


def _write_minimal_docx(path: str, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )


def _cli_service(registry_path: str, db_path: str) -> CliIntegrationService:
    audit_store = AuditEventStore(f"{db_path}.audit.sqlite3")
    return CliIntegrationService(
        adapter=create_cli_adapter_plugin(transcript_store=audit_store),
        transcript_store=audit_store,
        registry_path=registry_path,
        registry_store=ExternalCapabilityRegistryStore(db_path),
    )


def test_cli_registration_survives_service_reconstruction_and_writes_current_history_and_runtime_tables() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = f"{tmpdir}/cli_tools.json"
        db_path = f"{tmpdir}/core.sqlite3"
        tool_name = f"real-cli-persist-{uuid4().hex[:8]}"
        service = _cli_service(registry_path, db_path)
        response = service.register_tool(
            CliToolRegistrationConfig(
                tool_name=tool_name,
                command_executable="/bin/echo",
                description="Real CLI persistence verification.",
                read_only_flag=True,
                documentation_learning_required=False,
                health_probe_args=["health-ok"],
                help_probe_args=["help-ok"],
                version_probe_args=["version-ok"],
            )
        )
        assert response.status == "ok"
        assert any(item.command_name == tool_name for item in service.list_tools())
        current_rows = _rows(db_path, "cli_tool_registrations")
        assert len(current_rows) == 1
        assert current_rows[0]["asset_id"] == tool_name
        assert current_rows[0]["status"] == "active"
        assert tool_name in current_rows[0]["payload_json"]
        history_rows = _rows(db_path, "cli_tool_registration_history")
        assert any(row["asset_id"] == tool_name and row["action"] == "register" for row in history_rows)

        call = service.test_call(tool_name, arguments=["crud-readback"])
        assert call.status == "ok"
        assert call.data.stdout.strip() == "crud-readback"
        runtime_rows = _rows(db_path, "cli_tool_runtime_logs")
        assert len(runtime_rows) == 1
        assert runtime_rows[0]["asset_id"] == tool_name
        assert runtime_rows[0]["status"] == "success"
        assert "crud-readback" in runtime_rows[0]["request_json"]

        restored = _cli_service(registry_path, db_path)
        restored_tools = restored.list_tools()
        assert any(item.command_name == tool_name and item.status == "active" for item in restored_tools)
        assert restored.delete_tool(tool_name) is True
        assert _rows(db_path, "cli_tool_registrations") == []
        delete_history = _rows(db_path, "cli_tool_registration_history")
        assert any(row["asset_id"] == tool_name and row["action"] == "delete" for row in delete_history)


def test_external_connector_registration_survives_service_reconstruction_and_writes_current_history_and_runtime_tables() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = f"{tmpdir}/external_connectors.json"
        db_path = f"{tmpdir}/core.sqlite3"
        connector_id = f"real-file-persist-{uuid4().hex[:8]}"
        service = ExternalConnectorService(
            registry_path=registry_path,
            registry_store=ExternalCapabilityRegistryStore(db_path),
        )
        created = service.register_connector(
            ConnectorRegistrationRequest(
                connector_id=connector_id,
                connector_type=ConnectorType.FILE_APP,
                target_app="local-files",
                display_name="Real File Persistence Connector",
                description="Real external connector persistence verification.",
                connection_config={"root_path": "/private/tmp"},
                permission_scope={"read": True, "write": False, "allowed_paths": ["/private/tmp"]},
                profile_level=ConnectorProfileLevel.VERIFIABLE,
            )
        )
        assert created.connector_id == connector_id
        assert created.status == "active"
        assert any(item.connector_id == connector_id for item in service.list_connectors())
        current_rows = _rows(db_path, "external_connector_registrations")
        assert len(current_rows) == 1
        assert current_rows[0]["asset_id"] == connector_id
        assert current_rows[0]["status"] == "active"
        assert "Real File Persistence Connector" in current_rows[0]["payload_json"]

        restored = ExternalConnectorService(
            registry_path=registry_path,
            registry_store=ExternalCapabilityRegistryStore(db_path),
        )
        restored_connectors = restored.list_connectors()
        assert any(
            item.connector_id == connector_id
            and item.display_name == "Real File Persistence Connector"
            and item.status == "active"
            for item in restored_connectors
        )
        result = restored.health_check(connector_id)
        assert result.connector_id == connector_id
        assert result.health_status in {"healthy", "unhealthy"}
        assert restored.delete_connector(connector_id) == {"deleted": True, "connector_id": connector_id}
        assert _rows(db_path, "external_connector_registrations") == []
        history_rows = _rows(db_path, "external_connector_registration_history")
        assert {row["action"] for row in history_rows} >= {"register", "delete"}


def test_agent_registration_survives_service_reconstruction_and_writes_current_history_tables() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/core.sqlite3"
        store = ExternalCapabilityRegistryStore(db_path)
        service = AgentCoordinationService(registry_store=store)
        asset = asyncio.run(
            service.register_agent(
                AgentRegistrationRequest(
                    name="real-agent-registry",
                    agent_name="Real Agent Registry",
                    version="1.0.0",
                    function_description="Real DB registration verification.",
                    endpoint="http://127.0.0.1:9/agent",
                    role_tag="verification",
                    trust_level=AgentTrustLevel.PENDING,
                    scope=["read"],
                    adapter_type="http_json",
                    adapter_config={},
                )
            )
        )
        assert asset.status == AgentStatus.OFFLINE
        current_rows = _rows(db_path, "agent_registrations")
        assert len(current_rows) == 1
        assert current_rows[0]["asset_id"] == asset.agent_id
        assert current_rows[0]["status"] == "offline"
        assert "Real Agent Registry" in current_rows[0]["payload_json"]
        assert any(row["action"] == "register" for row in _rows(db_path, "agent_registration_history"))

        restored = AgentCoordinationService(registry_store=ExternalCapabilityRegistryStore(db_path))
        assert restored.manager.get_asset(asset.agent_id).agent_name == "Real Agent Registry"
        assert asyncio.run(restored.unregister_agent(asset.agent_id)) is True
        assert _rows(db_path, "agent_registrations") == []
        assert any(row["action"] == "delete" for row in _rows(db_path, "agent_registration_history"))


def test_mcp_http_registration_invocation_and_db_readback_are_real() -> None:
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
                    "description": "Echo real HTTP MCP arguments.",
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

    with tempfile.TemporaryDirectory() as tmpdir, live_http_server(app) as base_url:
        db_path = f"{tmpdir}/core.sqlite3"
        audit_store = AuditEventStore(f"{tmpdir}/mcp-audit.sqlite3")
        adapter = McpAdapterPlugin(
            plugin_id="mcp-real-http-registry-adapter",
            version="1.0.0",
            feature_code="real.mcp.registry",
            is_concurrency_safe=True,
            lifecycle_status=PluginLifecycleStatus.ACTIVE,
            health_status=PluginHealthStatus.HEALTHY,
            rollback_conditions=["mcp_regression"],
            revocation_reasons=["mcp_disabled"],
            server_configs=[],
        )
        adapter.attach_runtime(
            client_factory=lambda _config: HttpJsonMcpTransportClient(timeout_seconds=2.0),
            transcript_store=audit_store,
            cognitive_registry=CognitiveToolRegistry(transcript_store=audit_store),
            execution_registry=ExecutionDomainRegistry(),
        )
        service = McpIntegrationService(
            adapter=adapter,
            registry_path=f"{tmpdir}/mcp_servers.json",
            registry_store=ExternalCapabilityRegistryStore(db_path),
        )
        server_id = f"real-http-mcp-{uuid4().hex[:8]}"
        state = service.register_server(
            McpServerConfig(
                server_id=server_id,
                transport_type="http",
                command=base_url,
                documentation_learning_required=False,
                tool_bindings=[
                    McpToolBindingConfig(
                        tool_name="echo",
                        domain="cognitive",
                        read_only=True,
                        side_effect_free=True,
                        mutates_state=False,
                    )
                ],
            )
        )
        assert state.server_id == server_id
        assert state.status == "online"
        assert state.tool_count == 1
        current_rows = _rows(db_path, "mcp_server_registrations")
        assert len(current_rows) == 1
        assert current_rows[0]["asset_id"] == server_id
        assert current_rows[0]["status"] == "online"

        result = service.test_call(server_id, tool_name="echo", arguments={"value": "db-runtime-check"})
        assert result["status"] == "completed"
        assert result["data"]["arguments"]["value"] == "db-runtime-check"
        runtime_rows = _rows(db_path, "mcp_server_runtime_logs")
        assert len(runtime_rows) == 1
        assert runtime_rows[0]["asset_id"] == server_id
        assert runtime_rows[0]["status"] == "completed"
        assert "db-runtime-check" in runtime_rows[0]["request_json"]

        restored = McpIntegrationService(
            adapter=adapter,
            registry_path=f"{tmpdir}/mcp_servers.json",
            registry_store=ExternalCapabilityRegistryStore(db_path),
        )
        assert any(item.server_id == server_id for item in restored.list_servers())


def test_cli_web_api_register_query_invoke_delete_persists_to_independent_tables_with_requests() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/core.sqlite3"
        service = _cli_service(f"{tmpdir}/cli_tools.json", db_path)
        app = FastAPI()
        app.state.cli_service = service
        app.include_router(cli_router.router, prefix="/api/web")
        tool_name = f"api-cli-{uuid4().hex[:8]}"

        with live_http_server(app) as base_url:
            created = requests.post(
                f"{base_url}/api/web/cli-tools/register",
                json={
                    "tool_name": tool_name,
                    "command_executable": "/bin/echo",
                    "description": "Real CLI Web API database verification.",
                    "read_only_flag": True,
                    "documentation_learning_required": False,
                    "health_probe_args": ["health-ok"],
                    "help_probe_args": ["help-ok"],
                    "version_probe_args": ["version-ok"],
                },
                timeout=10,
            )
            assert created.status_code == 200
            assert created.json()["command_name"] == tool_name
            assert created.json()["status"] == "active"
            assert _rows(db_path, "cli_tool_registrations")[0]["asset_id"] == tool_name
            assert any(row["action"] == "register" for row in _rows(db_path, "cli_tool_registration_history"))

            listed = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
            assert listed.status_code == 200
            matches = [item for item in listed.json() if item["command_name"] == tool_name]
            assert len(matches) == 1
            assert matches[0]["description"] == "Real CLI Web API database verification."

            invoked = requests.post(
                f"{base_url}/api/web/cli-tools/{tool_name}/test-call",
                json={"arguments": ["api-runtime-check"], "timeout_seconds": 10},
                timeout=10,
            )
            assert invoked.status_code == 200
            assert invoked.json()["status"] == "success"
            assert invoked.json()["stdout"].strip() == "api-runtime-check"
            runtime_rows = _rows(db_path, "cli_tool_runtime_logs")
            assert len(runtime_rows) == 1
            assert runtime_rows[0]["asset_id"] == tool_name
            assert runtime_rows[0]["status"] == "success"
            assert "api-runtime-check" in runtime_rows[0]["request_json"]

            deleted = requests.delete(f"{base_url}/api/web/cli-tools/{tool_name}", timeout=10)
            assert deleted.status_code == 200
            assert deleted.json() == {"success": True, "tool_name": tool_name}
            listed_after_delete = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
            assert listed_after_delete.status_code == 200
            assert all(item["command_name"] != tool_name for item in listed_after_delete.json())
            assert _rows(db_path, "cli_tool_registrations") == []
            assert any(row["action"] == "delete" for row in _rows(db_path, "cli_tool_registration_history"))


def test_mcp_web_api_register_query_invoke_delete_persists_to_independent_tables_with_requests() -> None:
    mcp_backend = FastAPI()

    @mcp_backend.get("/health")
    def health() -> dict:
        return {"ok": True}

    @mcp_backend.get("/tools")
    def tools() -> dict:
        return {
            "tools": [
                {
                    "tool_name": "echo",
                    "description": "Echo real MCP Web API arguments.",
                    "input_schema": {"type": "object"},
                    "mutates_state": False,
                    "read_only_hint": True,
                }
            ]
        }

    @mcp_backend.post("/tools/echo/call")
    async def call(request: Request) -> dict:
        payload = await request.json()
        return {"accepted": True, "arguments": payload.get("arguments", {})}

    with tempfile.TemporaryDirectory() as tmpdir, live_http_server(mcp_backend) as mcp_base_url:
        db_path = f"{tmpdir}/core.sqlite3"
        audit_store = AuditEventStore(f"{tmpdir}/mcp-api-audit.sqlite3")
        adapter = McpAdapterPlugin(
            plugin_id="mcp-real-api-registry-adapter",
            version="1.0.0",
            feature_code="real.mcp.api.registry",
            is_concurrency_safe=True,
            lifecycle_status=PluginLifecycleStatus.ACTIVE,
            health_status=PluginHealthStatus.HEALTHY,
            rollback_conditions=["mcp_regression"],
            revocation_reasons=["mcp_disabled"],
            server_configs=[],
        )
        adapter.attach_runtime(
            client_factory=lambda _config: HttpJsonMcpTransportClient(timeout_seconds=2.0),
            transcript_store=audit_store,
            cognitive_registry=CognitiveToolRegistry(transcript_store=audit_store),
            execution_registry=ExecutionDomainRegistry(),
        )
        service = McpIntegrationService(
            adapter=adapter,
            registry_path=f"{tmpdir}/mcp_servers.json",
            registry_store=ExternalCapabilityRegistryStore(db_path),
        )
        app = FastAPI()
        app.state.mcp_service = service
        app.include_router(mcp_router.router, prefix="/api/web")
        server_id = f"api-mcp-{uuid4().hex[:8]}"

        with live_http_server(app) as base_url:
            created = requests.post(
                f"{base_url}/api/web/mcp-servers/register",
                json={
                    "server_id": server_id,
                    "transport_type": "http",
                    "command": mcp_base_url,
                    "documentation_learning_required": False,
                    "tool_bindings": [
                        {
                            "tool_name": "echo",
                            "domain": "cognitive",
                            "read_only": True,
                            "side_effect_free": True,
                            "mutates_state": False,
                        }
                    ],
                },
                timeout=10,
            )
            assert created.status_code == 200
            assert created.json()["server_id"] == server_id
            assert created.json()["status"] == "online"
            assert _rows(db_path, "mcp_server_registrations")[0]["asset_id"] == server_id
            assert any(row["action"] == "register" for row in _rows(db_path, "mcp_server_registration_history"))

            listed = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
            assert listed.status_code == 200
            matches = [item for item in listed.json() if item["server_id"] == server_id]
            assert len(matches) == 1
            assert matches[0]["tool_count"] == 1
            assert matches[0]["status"] == "online"

            invoked = requests.post(
                f"{base_url}/api/web/mcp-servers/{server_id}/test-call",
                json={"tool_name": "echo", "arguments": {"value": "mcp-api-runtime-check"}},
                timeout=10,
            )
            assert invoked.status_code == 200
            assert invoked.json()["server_id"] == server_id
            assert invoked.json()["tool_name"] == "echo"
            assert invoked.json()["payload"]["status"] == "completed"
            assert invoked.json()["payload"]["data"]["arguments"]["value"] == "mcp-api-runtime-check"
            runtime_rows = _rows(db_path, "mcp_server_runtime_logs")
            assert len(runtime_rows) == 1
            assert runtime_rows[0]["asset_id"] == server_id
            assert runtime_rows[0]["status"] == "completed"
            assert "mcp-api-runtime-check" in runtime_rows[0]["request_json"]

            deleted = requests.delete(f"{base_url}/api/web/mcp-servers/{server_id}", timeout=10)
            assert deleted.status_code == 200
            assert deleted.json() == {"success": True, "server_id": server_id}
            listed_after_delete = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
            assert listed_after_delete.status_code == 200
            assert all(item["server_id"] != server_id for item in listed_after_delete.json())
            assert _rows(db_path, "mcp_server_registrations") == []
            assert any(row["action"] == "delete" for row in _rows(db_path, "mcp_server_registration_history"))


def test_external_connector_web_api_register_query_invoke_delete_persists_to_independent_tables_with_requests() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/core.sqlite3"
        doc_path = f"{tmpdir}/source.docx"
        _write_minimal_docx(doc_path, "external connector api readback")
        service = ExternalConnectorService(
            registry_path=f"{tmpdir}/external_connectors.json",
            registry_store=ExternalCapabilityRegistryStore(db_path),
        )
        app = FastAPI()
        app.state.external_connector_service = service
        app.include_router(external_connectors_router.router, prefix="/api/web")
        connector_id = f"api-file-{uuid4().hex[:8]}"

        with live_http_server(app) as base_url:
            created = requests.post(
                f"{base_url}/api/web/external-connectors",
                json={
                    "connector_id": connector_id,
                    "connector_type": "file_app",
                    "target_app": "local-files",
                    "display_name": "Real External Connector API",
                    "description": "Real external connector API database verification.",
                    "connection_config": {"base_path": tmpdir},
                    "permission_scope": {"allowed_roots": [tmpdir]},
                    "profile_level": "verifiable",
                },
                timeout=10,
            )
            assert created.status_code == 200
            assert created.json()["connector_id"] == connector_id
            assert created.json()["status"] == "active"
            assert _rows(db_path, "external_connector_registrations")[0]["asset_id"] == connector_id
            assert any(row["action"] == "register" for row in _rows(db_path, "external_connector_registration_history"))

            listed = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
            assert listed.status_code == 200
            matches = [item for item in listed.json() if item["connector_id"] == connector_id]
            assert len(matches) == 1
            assert matches[0]["display_name"] == "Real External Connector API"

            invoked = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={"capability": "read_document", "arguments": {"path": doc_path}},
                timeout=10,
            )
            assert invoked.status_code == 200
            assert invoked.json()["status"] == "success"
            assert "external connector api readback" in invoked.json()["output_summary"]["text"]
            runtime_rows = _rows(db_path, "external_connector_runtime_logs")
            assert len(runtime_rows) == 1
            assert runtime_rows[0]["asset_id"] == connector_id
            assert runtime_rows[0]["status"] == "success"
            assert doc_path in runtime_rows[0]["request_json"]

            deleted = requests.delete(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
            assert deleted.status_code == 200
            assert deleted.json() == {"deleted": True, "connector_id": connector_id}
            listed_after_delete = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
            assert listed_after_delete.status_code == 200
            assert all(item["connector_id"] != connector_id for item in listed_after_delete.json())
            assert _rows(db_path, "external_connector_registrations") == []
            assert any(row["action"] == "delete" for row in _rows(db_path, "external_connector_registration_history"))
