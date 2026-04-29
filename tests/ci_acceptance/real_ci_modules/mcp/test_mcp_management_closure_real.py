from __future__ import annotations

from uuid import uuid4

import requests
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from tests.ci_acceptance.conftest import _AcceptanceTranscriptStore
from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.http_transport import HttpJsonMcpTransportClient
from zentex.mcp.service import McpIntegrationService
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry, ExecutionDomainRegistry


def _install_real_http_mcp_service(acceptance_app: FastAPI) -> None:
    transcript_store = acceptance_app.state.transcript_store
    assert isinstance(transcript_store, _AcceptanceTranscriptStore)
    adapter = McpAdapterPlugin(
        plugin_id="mcp-feature64-adapter",
        version="1.0.0",
        feature_code="feature64.mcp",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["feature64_regression"],
        revocation_reasons=["feature64_disabled"],
        server_configs=[],
    )
    adapter.attach_runtime(
        client_factory=lambda _config: HttpJsonMcpTransportClient(timeout_seconds=1.0),
        transcript_store=transcript_store,
        cognitive_registry=CognitiveToolRegistry(transcript_store=transcript_store),
        execution_registry=ExecutionDomainRegistry(),
    )
    acceptance_app.state.mcp_service = McpIntegrationService(adapter=adapter)


def _mcp_server_app() -> FastAPI:
    app = FastAPI()
    app.state.notes = {}
    app.state.schema_revision = 1
    app.state.online = True

    def _tools_for(server_id: str) -> list[dict[str, object]]:
        inspect_schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "mode": {"type": "string"},
                "note_id": {"type": "string"},
            },
        }
        if app.state.schema_revision >= 2 and server_id == "primary":
            inspect_schema = {
                **inspect_schema,
                "required": ["mode"],
                "properties": {**inspect_schema["properties"], "revision": {"type": "integer"}},
            }
        tools: list[dict[str, object]] = [
            {
                "tool_name": "inspect",
                "description": f"Inspect {server_id} notes",
                "input_schema": inspect_schema,
                "mutates_state": False,
                "read_only_hint": True,
            }
        ]
        if server_id == "primary":
            tools.append(
                {
                    "tool_name": "write_note",
                    "description": "Create a note in the MCP server",
                    "input_schema": {
                        "type": "object",
                        "required": ["note_id", "content"],
                        "properties": {
                            "note_id": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                    "mutates_state": True,
                    "read_only_hint": False,
                }
            )
        return tools

    @app.get("/{server_id}/health")
    def health(server_id: str) -> dict[str, object]:
        if not app.state.online:
            return JSONResponse(status_code=503, content={"ok": False, "server_id": server_id})
        return {"ok": True, "server_id": server_id}

    @app.get("/{server_id}/tools")
    def tools(server_id: str) -> dict[str, object]:
        return {"tools": _tools_for(server_id)}

    @app.post("/{server_id}/tools/{tool_name}/call", response_model=None)
    def call_tool(server_id: str, tool_name: str, payload: dict[str, object]):
        arguments = payload.get("arguments")
        assert isinstance(arguments, dict)
        trace_id = str(payload.get("trace_id"))
        mode = arguments.get("mode")
        if mode == "bad_json":
            return PlainTextResponse("this is not json")
        if mode == "empty":
            return Response(status_code=200, content=b"")
        if mode == "forbidden":
            return JSONResponse(status_code=403, content={"error": "permission denied"})
        if tool_name == "write_note":
            note_id = str(arguments["note_id"])
            content = str(arguments["content"])
            app.state.notes[note_id] = content
            return {
                "summary": "note written",
                "server_id": server_id,
                "tool_name": tool_name,
                "trace_id": trace_id,
                "note_id": note_id,
                "content": content,
            }
        if tool_name == "inspect":
            note_id = arguments.get("note_id")
            return {
                "summary": "inspection complete",
                "server_id": server_id,
                "tool_name": tool_name,
                "trace_id": trace_id,
                "notes": dict(app.state.notes),
                "note": app.state.notes.get(str(note_id)) if note_id else None,
                "schema_revision": app.state.schema_revision,
            }
        return JSONResponse(status_code=404, content={"error": "unknown tool"})

    return app


def test_feature64_mcp_management_closure_real_requests(acceptance_app: FastAPI) -> None:
    _install_real_http_mcp_service(acceptance_app)
    suffix = uuid4().hex[:8]
    primary_id = f"feature64-primary-{suffix}"
    duplicate_id = f"feature64-duplicate-{suffix}"
    incompatible_id = f"feature64-incompatible-{suffix}"
    note_id = f"note-{suffix}"
    mcp_app = _mcp_server_app()

    with live_http_server(mcp_app) as mcp_base_url, live_http_server(acceptance_app) as base_url:
        primary_register = requests.post(
            f"{base_url}/api/web/mcp-servers/register",
            json={
                "server_id": primary_id,
                "name": "Feature 64 primary MCP",
                "description": "Real HTTP MCP server for feature 64",
                "version": "1.0.0",
                "protocol_version": "2024-11-05",
                "transport_type": "http",
                "command": f"{mcp_base_url}/primary",
                "scope": ["read", "write"],
                "auth_mode": "none",
            },
            timeout=10,
        )
        assert primary_register.status_code == 200, primary_register.text
        primary_payload = primary_register.json()
        assert primary_payload["server_id"] == primary_id
        assert primary_payload["status"] == "online"
        assert primary_payload["tool_count"] == 2
        primary_tools = {tool["tool_name"]: tool for tool in primary_payload["tools"]}
        assert primary_tools["inspect"]["mapped_domain"] == "cognitive"
        assert primary_tools["write_note"]["mapped_domain"] == "execution"
        assert primary_tools["write_note"]["requires_cloud_audit"] is True

        duplicate_register = requests.post(
            f"{base_url}/api/web/mcp-servers/register",
            json={
                "server_id": duplicate_id,
                "protocol_version": "2024-11-05",
                "transport_type": "http",
                "command": f"{mcp_base_url}/duplicate",
                "scope": ["read"],
                "auth_mode": "none",
            },
            timeout=10,
        )
        assert duplicate_register.status_code == 200, duplicate_register.text
        assert duplicate_register.json()["tool_count"] == 1
        assert duplicate_register.json()["tools"][0]["tool_name"] == "inspect"

        incompatible = requests.post(
            f"{base_url}/api/web/mcp-servers/register",
            json={
                "server_id": incompatible_id,
                "protocol_version": "1999-01-01",
                "transport_type": "http",
                "command": f"{mcp_base_url}/primary",
                "scope": ["read"],
                "auth_mode": "none",
            },
            timeout=10,
        )
        assert incompatible.status_code == 400
        assert "Unsupported MCP protocol_version" in incompatible.text

        duplicate_again = requests.post(
            f"{base_url}/api/web/mcp-servers/register",
            json={
                "server_id": primary_id,
                "protocol_version": "2024-11-05",
                "transport_type": "http",
                "command": f"{mcp_base_url}/primary",
                "scope": ["read", "write"],
                "auth_mode": "none",
            },
            timeout=10,
        )
        assert duplicate_again.status_code == 400
        assert "already registered" in duplicate_again.text

        servers = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
        assert servers.status_code == 200
        server_map = {item["server_id"]: item for item in servers.json() if item["server_id"] in {primary_id, duplicate_id, incompatible_id}}
        assert set(server_map) == {primary_id, duplicate_id}
        assert server_map[primary_id]["status"] == "online"
        assert server_map[duplicate_id]["status"] == "online"

        write_call = requests.post(
            f"{base_url}/api/web/mcp-servers/{primary_id}/test-call",
            json={"tool_name": "write_note", "arguments": {"note_id": note_id, "content": "feature64-written"}},
            timeout=10,
        )
        assert write_call.status_code == 200, write_call.text
        write_payload = write_call.json()["payload"]
        assert write_payload["status"] == "completed"
        assert write_payload["data"]["content"] == "feature64-written"

        inspect_call = requests.post(
            f"{base_url}/api/web/mcp-servers/{primary_id}/test-call",
            json={"tool_name": "inspect", "arguments": {"note_id": note_id}},
            timeout=10,
        )
        assert inspect_call.status_code == 200, inspect_call.text
        inspect_payload = inspect_call.json()["payload"]
        assert inspect_payload["status"] == "completed"
        assert inspect_payload["data"]["note"] == "feature64-written"
        assert inspect_payload["data"]["notes"][note_id] == "feature64-written"

        for mode, error_code in {
            "bad_json": "mcp_bad_json",
            "empty": "mcp_empty_response",
            "forbidden": "mcp_permission_denied",
        }.items():
            failure = requests.post(
                f"{base_url}/api/web/mcp-servers/{primary_id}/test-call",
                json={"tool_name": "inspect", "arguments": {"mode": mode}},
                timeout=10,
            )
            assert failure.status_code == 200, failure.text
            failure_payload = failure.json()["payload"]
            assert failure_payload["status"] == "failed"
            assert failure_payload["error_code"] == error_code
            assert failure_payload["server_id"] == primary_id
            assert failure_payload["tool_name"] == "inspect"

        diagnostics = requests.get(f"{base_url}/api/web/mcp-servers/closure/diagnostics", timeout=10)
        assert diagnostics.status_code == 200, diagnostics.text
        diagnostic_payload = diagnostics.json()
        checks = {item["name"]: item for item in diagnostic_payload["checks"]}
        assert checks["server_registration_validation"]["passed"] is True
        assert checks["protocol_version_compatibility"]["passed"] is True
        assert checks["transport_health_detection"]["passed"] is True
        assert checks["tool_schema_consistency"]["passed"] is True
        assert checks["audit_chain_completeness"]["passed"] is True
        assert checks["tool_call_failure_classification"]["passed"] is True
        assert diagnostic_payload["metrics"]["server_count"] == 2
        assert diagnostic_payload["metrics"]["online_server_count"] == 2
        assert diagnostic_payload["metrics"]["tool_count"] == 3
        assert diagnostic_payload["metrics"]["registration_rejection_count"] >= 2
        assert diagnostic_payload["completion"]["registration_complete"] is True
        assert diagnostic_payload["completion"]["handshake_complete"] is True
        assert diagnostic_payload["completion"]["real_completion"] is True
        issue_codes = {item["code"] for item in diagnostic_payload["issues"]}
        assert "duplicate_tool_definition" in issue_codes
        assert "classified_mcp_error" in issue_codes

        mcp_app.state.schema_revision = 2
        drift = requests.post(f"{base_url}/api/web/mcp-servers/{primary_id}/activate", timeout=10)
        assert drift.status_code == 200, drift.text
        drift_payload = drift.json()
        assert drift_payload["status"] == "degraded"
        assert "schema drift" in drift_payload["error_message"]

        post_drift_health = requests.get(f"{base_url}/api/web/mcp-servers/{primary_id}/health", timeout=10)
        assert post_drift_health.status_code == 200
        assert post_drift_health.json()["healthy"] is False
        assert post_drift_health.json()["status"] == "degraded"

        post_drift_diagnostics = requests.get(f"{base_url}/api/web/mcp-servers/closure/diagnostics", timeout=10)
        assert post_drift_diagnostics.status_code == 200
        post_drift_payload = post_drift_diagnostics.json()
        post_drift_issue_codes = {item["code"] for item in post_drift_payload["issues"]}
        assert "schema_drift" in post_drift_issue_codes
        assert post_drift_payload["metrics"]["schema_drift_count"] >= 1

        fault_matrix = requests.post(f"{base_url}/api/web/mcp-servers/closure/fault-injection", timeout=10)
        assert fault_matrix.status_code == 200, fault_matrix.text
        fault_payload = fault_matrix.json()
        assert fault_payload["passed"] is True
        fault_cases = {item["name"]: item for item in fault_payload["cases"]}
        assert fault_cases["bad_json_classified"]["passed"] is True
        assert fault_cases["empty_response_classified"]["passed"] is True
        assert fault_cases["version_incompatibility_detector_ran"]["passed"] is True
        assert fault_cases["schema_drift_detector_ran"]["passed"] is True
        assert fault_cases["permission_denial_classified"]["passed"] is True
        assert fault_cases["duplicate_tool_conflict_detector_ran"]["passed"] is True
        assert fault_cases["audit_chain_verified"]["passed"] is True

    audit_payloads = [
        entry.get("payload") or {}
        for entry in acceptance_app.state.transcript_store.entries
        if (entry.get("payload") or {}).get("server_id") in {primary_id, duplicate_id, incompatible_id}
    ]
    assert any(item.get("status") == "rejected" and item.get("error_code") == "mcp_protocol_incompatible" for item in audit_payloads)
    assert any(item.get("status") == "rejected" and item.get("error_code") == "mcp_duplicate_server" for item in audit_payloads)
    assert any(item.get("status") == "completed" and item.get("tool_name") == "write_note" for item in audit_payloads)
    assert any(item.get("error_code") == "mcp_bad_json" for item in audit_payloads)
    assert any(item.get("error_code") == "mcp_empty_response" for item in audit_payloads)
    assert any(item.get("error_code") == "mcp_permission_denied" for item in audit_payloads)
    assert any(item.get("error_code") == "mcp_schema_drift" for item in audit_payloads)
