from __future__ import annotations

import sys
import tempfile
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
import requests

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.agents.service import AgentCoordinationService
from zentex.cli.adapter import create_cli_adapter_plugin
from zentex.cli.service import CliIntegrationService
from zentex.external_capabilities import ExternalCapabilityRegistryStore
from zentex.external_connectors.service import ExternalConnectorService
from zentex.kernel import AuditEventStore
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.http_transport import HttpJsonMcpTransportClient
from zentex.mcp.service import McpIntegrationService
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry, ExecutionDomainRegistry
from zentex.web_console.router import api_router


def _real_runtime_app(real_ci_runtime) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    app.state.reflection_service = real_ci_runtime.reflection_service
    app.state.learning_service = real_ci_runtime.learning_service
    app.state.memory_service = real_ci_runtime.memory_service
    app.state.audit_service = real_ci_runtime.audit_service
    app.state.task_service = real_ci_runtime.task_service
    app.state.agent_coordination_service = real_ci_runtime.agent_service
    app.state.agent_service = real_ci_runtime.agent_service
    app.state.default_workspace = "/Users/harry/Documents/git/AnimoCerebro-V2"
    return app


def _module_data(modules_payload: dict, module_id: str) -> dict:
    module = modules_payload["modules"][module_id]
    data = module.get("data")
    return data if isinstance(data, dict) else module


def _strict_asset_inventory_app(real_ci_runtime, tmpdir: str) -> FastAPI:
    app = _real_runtime_app(real_ci_runtime)
    registry_store = ExternalCapabilityRegistryStore(f"{tmpdir}/q3-assets.sqlite3")
    audit_store = AuditEventStore(f"{tmpdir}/q3-assets-audit.sqlite3")
    app.state.agent_coordination_service = AgentCoordinationService(
        transcript_store=audit_store,
        registry_store=registry_store,
    )
    app.state.agent_service = app.state.agent_coordination_service
    app.state.cli_service = CliIntegrationService(
        adapter=create_cli_adapter_plugin(transcript_store=audit_store),
        transcript_store=audit_store,
        registry_path=f"{tmpdir}/cli_tools.json",
        registry_store=registry_store,
    )
    mcp_adapter = McpAdapterPlugin(
        plugin_id="q3-real-http-mcp-adapter",
        version="1.0.0",
        feature_code="q3.real.mcp.inventory",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["q3_mcp_inventory_regression"],
        revocation_reasons=["q3_mcp_inventory_disabled"],
        server_configs=[],
    )
    mcp_adapter.attach_runtime(
        client_factory=lambda _config: HttpJsonMcpTransportClient(timeout_seconds=2.0),
        transcript_store=audit_store,
        cognitive_registry=CognitiveToolRegistry(transcript_store=audit_store),
        execution_registry=ExecutionDomainRegistry(),
    )
    app.state.mcp_service = McpIntegrationService(
        adapter=mcp_adapter,
        registry_path=f"{tmpdir}/mcp_servers.json",
        registry_store=registry_store,
    )
    app.state.external_connector_service = ExternalConnectorService(
        transcript_store=audit_store,
        registry_path=f"{tmpdir}/external_connectors.json",
        registry_store=registry_store,
    )
    return app


def test_q3_web_run_api_uses_real_requests_and_persists_business_modules(real_ci_runtime) -> None:
    app = _real_runtime_app(real_ci_runtime)

    with live_http_server(app) as base_url:
        run_response = requests.post(
            f"{base_url}/api/web/nine-questions/q3/run",
            json={"force_refresh": True, "single_only": True},
            timeout=540,
        )
        assert run_response.status_code == 200, run_response.text
        run_payload = run_response.json()
        assert run_payload["started"] is True
        assert run_payload["refresh_reason"] == "single_nine_question_reexecuted:q3"
        assert str(run_payload["trace_id"]).strip()
        assert int(run_payload["snapshot_version"]) >= 1
        assert isinstance(run_payload["revision"], int)

        modules_response = requests.get(
            f"{base_url}/api/web/nine-questions/q3/modules",
            timeout=30,
        )
        assert modules_response.status_code == 200, modules_response.text
        modules_payload = modules_response.json()

        detail_response = requests.get(
            f"{base_url}/api/web/nine-questions/q3",
            timeout=30,
        )
        assert detail_response.status_code == 200, detail_response.text
        detail_payload = detail_response.json()

    assert modules_payload["question_id"] == "q3"
    assert modules_payload["status"]["status"] == "completed"
    module_map = modules_payload["modules"]
    assert isinstance(module_map, dict) and module_map
    required_modules = {
        "workspace_permission_inventory",
        "cognitive_tools_inventory",
        "execution_tools_inventory",
        "connected_agents_inventory",
        "cli_inventory",
        "mcp_inventory",
        "external_connectors_inventory",
        "memory_strategy_inventory",
        "q3_resource_sufficiency_inference",
    }
    assert required_modules.issubset(module_map.keys())
    for module_id in required_modules:
        module_entry = module_map[module_id]
        assert module_entry["status"] in {"completed", "ready"}, module_entry
        assert not str(module_entry.get("error_code") or "").strip(), module_entry
        assert not str(module_entry.get("error_message") or "").strip(), module_entry

    assert detail_payload["question_id"] == "q3"
    assert str(detail_payload["summary"]).strip()
    context_updates = detail_payload["context_updates"]
    diagnosis = context_updates["q3_execution_diagnosis"]
    assert diagnosis["authenticity_status"] == "completed"
    module_runs = diagnosis["module_runs"]
    assert isinstance(module_runs, list) and module_runs
    failed_runs = [
        item
        for item in module_runs
        if isinstance(item, dict)
        and (
            str(item.get("status") or "") not in {"completed", "ready"}
            or str(item.get("error_code") or "").strip()
            or str(item.get("error_message") or "").strip()
            or str(item.get("question_id") or "").strip().lower() != "q3"
        )
    ]
    assert failed_runs == []


def test_q3_web_run_api_reads_registered_cli_mcp_external_connectors_and_agents(real_ci_runtime) -> None:
    mcp_server = FastAPI()

    @mcp_server.get("/health")
    def health() -> dict:
        return {"ok": True}

    @mcp_server.get("/tools")
    def tools() -> dict:
        return {
            "tools": [
                {
                    "tool_name": "inspect",
                    "description": "Inspect Q3 registered MCP inventory over real HTTP.",
                    "input_schema": {"type": "object", "properties": {"x": {"type": "integer"}}},
                    "mutates_state": False,
                    "read_only_hint": True,
                }
            ]
        }

    @mcp_server.post("/tools/inspect/call")
    async def call(request: Request) -> dict:
        payload = await request.json()
        return {"status": "completed", "arguments": payload.get("arguments", {})}

    with tempfile.TemporaryDirectory() as tmpdir, live_http_server(mcp_server) as mcp_base_url:
        app = _strict_asset_inventory_app(real_ci_runtime, tmpdir)
        suffix = uuid4().hex[:8]
        cli_name = f"q3-real-cli-{suffix}"
        mcp_id = f"q3-real-mcp-{suffix}"
        connector_id = f"q3-real-connector-{suffix}"

        with live_http_server(app) as base_url:
            cli_register = requests.post(
                f"{base_url}/api/web/cli-tools/register",
                json={
                    "tool_name": cli_name,
                    "command_executable": sys.executable,
                    "command_args": ["-c", "print('q3 real cli inventory')"],
                    "description": "Q3 real CLI inventory registration.",
                    "read_only_flag": True,
                    "documentation_learning_required": False,
                    "health_probe_args": [],
                    "help_probe_args": [],
                    "version_probe_args": [],
                },
                timeout=10,
            )
            assert cli_register.status_code == 200, cli_register.text
            assert cli_register.json()["command_name"] == cli_name
            cli_list = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
            assert cli_list.status_code == 200, cli_list.text
            assert any(item["command_name"] == cli_name for item in cli_list.json())

            mcp_register = requests.post(
                f"{base_url}/api/web/mcp-servers/register",
                json={
                    "server_id": mcp_id,
                    "transport_type": "http",
                    "command": mcp_base_url,
                    "documentation_learning_required": False,
                    "tool_bindings": [{"tool_name": "inspect", "domain": "cognitive"}],
                },
                timeout=20,
            )
            assert mcp_register.status_code == 200, mcp_register.text
            assert mcp_register.json()["server_id"] == mcp_id
            assert mcp_register.json()["tool_count"] == 1
            mcp_list = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
            assert mcp_list.status_code == 200, mcp_list.text
            assert any(item["server_id"] == mcp_id and item["tool_count"] == 1 for item in mcp_list.json())

            connector_register = requests.post(
                f"{base_url}/api/web/external-connectors",
                json={
                    "connector_id": connector_id,
                    "connector_type": "file_app",
                    "target_app": "local-files",
                    "display_name": "Q3 Real External Connector",
                    "description": "Q3 real external connector inventory registration.",
                    "connection_config": {"root_path": tmpdir},
                    "permission_scope": {"read": True, "write": False, "allowed_paths": [tmpdir]},
                    "profile_level": "verifiable",
                },
                timeout=10,
            )
            assert connector_register.status_code == 200, connector_register.text
            assert connector_register.json()["connector_id"] == connector_id
            connector_list = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
            assert connector_list.status_code == 200, connector_list.text
            assert any(item["connector_id"] == connector_id for item in connector_list.json())

            agent_register = requests.post(
                f"{base_url}/api/web/agents/register",
                json={
                    "name": f"q3-real-agent-{suffix}",
                    "agent_name": "Q3 Real Registered Agent",
                    "version": "1.0.0",
                    "function_description": "Q3 real registered agent inventory.",
                    "endpoint": "local://q3-real-agent",
                    "role_tag": "q3_inventory",
                    "scope": ["q3_inventory"],
                },
                timeout=10,
            )
            assert agent_register.status_code == 200, agent_register.text
            agent_id = agent_register.json()["agent_id"]
            agent_list = requests.get(f"{base_url}/api/web/agents", timeout=10)
            assert agent_list.status_code == 200, agent_list.text
            assert any(item["agent_id"] == agent_id for item in agent_list.json())

            run_response = requests.post(
                f"{base_url}/api/web/nine-questions/q3/run",
                json={"force_refresh": True, "single_only": True},
                timeout=540,
            )
            assert run_response.status_code == 200, run_response.text
            modules_response = requests.get(f"{base_url}/api/web/nine-questions/q3/modules", timeout=30)
            assert modules_response.status_code == 200, modules_response.text
            modules_payload = modules_response.json()

    assert modules_payload["question_id"] == "q3"
    module_map = modules_payload["modules"]
    for module_id in {
        "cli_inventory",
        "mcp_inventory",
        "external_connectors_inventory",
        "connected_agents_inventory",
    }:
        assert module_id in module_map
        assert module_map[module_id]["status"] == "completed", module_map[module_id]
        assert not str(module_map[module_id].get("error_code") or "").strip(), module_map[module_id]

    cli_data = _module_data(modules_payload, "cli_inventory")
    assert cli_name in cli_data["available_cli_tools"]
    assert any(item["command_name"] == cli_name for item in cli_data["cli_tools"])

    mcp_data = _module_data(modules_payload, "mcp_inventory")
    assert mcp_id in mcp_data["available_mcp_servers"]
    assert any(item["server_id"] == mcp_id and item["tool_count"] == 1 for item in mcp_data["mcp_servers"])

    connector_data = _module_data(modules_payload, "external_connectors_inventory")
    assert connector_id in connector_data["available_external_connectors"]
    assert any(item["connector_id"] == connector_id for item in connector_data["external_connectors"])

    agent_data = _module_data(modules_payload, "connected_agents_inventory")
    assert any(item["agent_id"] == agent_id and item["status"] == "offline" for item in agent_data["connected_agents"])
