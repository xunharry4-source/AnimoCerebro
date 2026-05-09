from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.conftest import _AcceptanceTranscriptStore
from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.agents.auth import AgentAuthService, AgentCredentialVault
from zentex.common.database import DatabaseConnection
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.sdk_transport import OfficialMcpSdkTransportClient
from zentex.mcp.service import McpIntegrationService
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry, ExecutionDomainRegistry


DEFAULT_QUERY_TOOL = "API-get-self"
REAL_NOTION_CASE_PATH = Path(__file__).with_name("real_notion_mcp_case.local.json")


def _load_real_notion_case() -> dict[str, Any]:
    if not REAL_NOTION_CASE_PATH.exists():
        pytest.fail(
            "Real Notion MCP test is not configured; create "
            f"{REAL_NOTION_CASE_PATH} with api_key, register_arguments, query_arguments, "
            "and query_assertions. This private file represents the user submitting API key "
            "and business parameters through the web/API registration request body.",
            pytrace=False,
        )
    try:
        payload = json.loads(REAL_NOTION_CASE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"{REAL_NOTION_CASE_PATH} must be valid JSON: {exc}", pytrace=False)
    required = ["api_key", "query_arguments", "query_assertions"]
    missing = [key for key in required if key not in payload]
    if missing:
        pytest.fail(f"{REAL_NOTION_CASE_PATH} missing required keys: {', '.join(missing)}", pytrace=False)
    if str(payload["api_key"]).startswith("REPLACE_WITH_"):
        pytest.fail(f"{REAL_NOTION_CASE_PATH} still contains placeholder api_key; replace it with a real Notion API key", pytrace=False)
    if not isinstance(payload["query_assertions"], list) or not payload["query_assertions"]:
        pytest.fail("query_assertions must be a non-empty list of strict business result checks", pytrace=False)
    return payload


def _render_placeholders(value: Any, context: dict[str, str]) -> Any:
    if isinstance(value, str):
        rendered = value
        for key, replacement in context.items():
            rendered = rendered.replace("{" + key + "}", replacement)
        return rendered
    if isinstance(value, list):
        return [_render_placeholders(item, context) for item in value]
    if isinstance(value, dict):
        return {str(key): _render_placeholders(item, context) for key, item in value.items()}
    return value


def _extract_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise AssertionError(f"path '{path}' cannot index list at '{part}'") from exc
            continue
        if not isinstance(current, dict) or part not in current:
            raise AssertionError(f"path '{path}' missing at '{part}'")
        current = current[part]
    return current


def _assert_json_path_assertions(payload: dict[str, Any], assertions: list[dict[str, Any]]) -> None:
    assert assertions, "query assertions must not be empty"
    for assertion in assertions:
        path = assertion.get("path")
        assert isinstance(path, str) and path, f"assertion missing path: {assertion}"
        actual = _extract_path(payload, path)
        if "equals" in assertion:
            assert actual == assertion["equals"], f"{path}: expected {assertion['equals']!r}, got {actual!r}"
        elif "contains" in assertion:
            assert str(assertion["contains"]) in str(actual), (
                f"{path}: expected {actual!r} to contain {assertion['contains']!r}"
            )
        else:
            raise AssertionError(f"assertion must define equals or contains: {assertion}")


def _install_real_notion_mcp_service(acceptance_app: FastAPI, auth_service: AgentAuthService) -> None:
    transcript_store = acceptance_app.state.transcript_store
    assert isinstance(transcript_store, _AcceptanceTranscriptStore)
    adapter = McpAdapterPlugin(
        plugin_id="mcp-real-notion-adapter",
        version="1.0.0",
        feature_code="real.notion.mcp",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["real_notion_mcp_regression"],
        revocation_reasons=["real_notion_mcp_disabled"],
        server_configs=[],
    )

    def client_factory(_config: Any) -> Any:
        return OfficialMcpSdkTransportClient()

    adapter.attach_runtime(
        client_factory=client_factory,
        transcript_store=transcript_store,
        cognitive_registry=CognitiveToolRegistry(transcript_store=transcript_store),
        execution_registry=ExecutionDomainRegistry(),
        auth_service=auth_service,
    )
    acceptance_app.state.mcp_service = McpIntegrationService(adapter=adapter, auth_service=auth_service)


def test_real_notion_mcp_registers_emotion_and_reads_it_back_via_requests(request: pytest.FixtureRequest) -> None:
    case = _load_real_notion_case()
    transport = str(case.get("transport", "http"))
    if transport != "stdio":
        pytest.fail(
            "Notion API-key MCP test must use stdio @notionhq/notion-mcp-server. "
            "The hosted https://mcp.notion.com/mcp endpoint uses OAuth and rejects API-key bearer auth.",
            pytrace=False,
        )

    acceptance_app: FastAPI = request.getfixturevalue("acceptance_app")
    auth_service = AgentAuthService(
        AgentCredentialVault(
            DatabaseConnection(f"{request.getfixturevalue('tmp_path')}/notion-auth.sqlite3"),
            master_key="real-notion-mcp-master-key",
        )
    )
    original_auth_service = acceptance_app.state.agent_coordination_service.auth_service
    original_mcp_service = acceptance_app.state.mcp_service
    acceptance_app.state.agent_coordination_service.auth_service = auth_service
    _install_real_notion_mcp_service(acceptance_app, auth_service)
    suffix = uuid4().hex[:8]
    server_id = f"real-notion-{suffix}"
    credential_id = f"real-notion-cred-{suffix}"
    context = {"suffix": suffix}

    query_tool = str(case.get("query_tool") or DEFAULT_QUERY_TOOL)
    query_arguments = _render_placeholders(case["query_arguments"], context)
    query_assertions = _render_placeholders(case["query_assertions"], context)
    command = str(case.get("command") or "npx")
    args = _render_placeholders(case.get("args", ["-y", "@notionhq/notion-mcp-server"]), context)
    notion_version = str(case.get("notion_version", "2022-06-28"))
    notion_api_key = str(case["api_key"])
    auth_config: dict[str, Any] = {
        "type": "api_key",
        "credential_ref": credential_id,
        "inject": {
            "env": {
                "OPENAPI_MCP_HEADERS": (
                    '{"Authorization":"Bearer $auth.api_key",'
                    f'"Notion-Version":"{notion_version}"' + "}"
                )
            }
        },
    }

    try:
        with live_http_server(acceptance_app) as base_url:
            register_response = requests.post(
                f"{base_url}/api/web/mcp-servers/register",
                json={
                    "server_id": server_id,
                    "name": "Real Notion MCP",
                    "description": "Real Notion API-key MCP used for strict query verification",
                    "protocol_version": str(case.get("protocol_version", "2024-11-05")),
                    "transport_type": transport,
                    "command": command,
                    "args": args,
                    "env": {},
                    "scope": ["read"],
                    "auth_mode": "api_key",
                    "auth_config": auth_config,
                    "auth_credential": {
                        "credential_id": credential_id,
                        "credential_type": "api_key",
                        "secret_payload": {"api_key": notion_api_key},
                        "metadata": {"provider": "notion", "purpose": "real notion mcp api key read/write"},
                    },
                    "documentation_learning_required": False,
                },
                timeout=60,
            )
            assert register_response.status_code == 200, register_response.text
            registered = register_response.json()
            assert registered["server_id"] == server_id
            assert registered["status"] == "online"
            tool_names = {tool["tool_name"] for tool in registered["tools"]}
            assert query_tool in tool_names
            assert notion_api_key not in register_response.text
            listed_credentials_response = requests.get(
                f"{base_url}/api/web/integrations/mcp/{server_id}/credentials",
                timeout=30,
            )
            assert listed_credentials_response.status_code == 200, listed_credentials_response.text
            listed_credentials = listed_credentials_response.json()
            assert len(listed_credentials) == 1
            assert listed_credentials[0]["credential_id"] == credential_id
            assert listed_credentials[0]["credential_type"] == "api_key"
            assert listed_credentials[0]["metadata"]["provider"] == "notion"
            assert notion_api_key not in listed_credentials_response.text

            query_response = requests.post(
                f"{base_url}/api/web/mcp-servers/{server_id}/test-call",
                json={"tool_name": query_tool, "arguments": query_arguments},
                timeout=120,
            )
            assert query_response.status_code == 200, query_response.text
            query_payload = query_response.json()["payload"]
            assert query_payload["status"] == "completed", query_payload
            assert query_payload["error_code"] is None
            assert isinstance(query_assertions, list)
            _assert_json_path_assertions(query_payload, query_assertions)
            assert notion_api_key not in query_response.text

            health_response = requests.get(f"{base_url}/api/web/mcp-servers/{server_id}/health", timeout=30)
            assert health_response.status_code == 200, health_response.text
            health_payload = health_response.json()
            assert health_payload["status"] == "online"
            assert health_payload["healthy"] is True

            diagnostics_response = requests.get(f"{base_url}/api/web/mcp-servers/closure/diagnostics", timeout=30)
            assert diagnostics_response.status_code == 200, diagnostics_response.text
            diagnostics = diagnostics_response.json()
            checks = {item["name"]: item for item in diagnostics["checks"]}
            assert diagnostics["completion"]["registration_complete"] is True
            assert checks["transport_health_detection"]["passed"] is True
            assert checks["audit_chain_completeness"]["passed"] is True
    finally:
        acceptance_app.state.agent_coordination_service.auth_service = original_auth_service
        acceptance_app.state.mcp_service = original_mcp_service

    audit_payloads = [
        entry.get("payload") or {}
        for entry in acceptance_app.state.transcript_store.entries
        if (entry.get("payload") or {}).get("server_id") == server_id
    ]
    assert any(item.get("status") == "completed" and item.get("tool_name") == query_tool for item in audit_payloads)
