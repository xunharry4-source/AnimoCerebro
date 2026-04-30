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


DEFAULT_GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"
REAL_GITHUB_CASE_PATH = Path(__file__).with_name("real_github_mcp_case.local.json")


def _load_real_github_case() -> dict[str, Any]:
    if not REAL_GITHUB_CASE_PATH.exists():
        pytest.fail(
            "Real GitHub MCP test is not configured; create "
            f"{REAL_GITHUB_CASE_PATH} with api_key, query_tool, query_arguments, "
            "and query_assertions. This private file represents the user submitting API key "
            "and business query parameters through the web/API registration request body.",
            pytrace=False,
        )
    try:
        payload = json.loads(REAL_GITHUB_CASE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"{REAL_GITHUB_CASE_PATH} must be valid JSON: {exc}", pytrace=False)
    required = ["api_key", "query_tool", "query_arguments", "query_assertions"]
    missing = [key for key in required if key not in payload]
    if missing:
        pytest.fail(f"{REAL_GITHUB_CASE_PATH} missing required keys: {', '.join(missing)}", pytrace=False)
    if str(payload["api_key"]).startswith("REPLACE_WITH_"):
        pytest.fail(f"{REAL_GITHUB_CASE_PATH} still contains placeholder api_key; replace it with a real GitHub API key", pytrace=False)
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


def _install_real_github_mcp_service(acceptance_app: FastAPI, auth_service: AgentAuthService) -> None:
    transcript_store = acceptance_app.state.transcript_store
    assert isinstance(transcript_store, _AcceptanceTranscriptStore)
    adapter = McpAdapterPlugin(
        plugin_id="mcp-real-github-adapter",
        version="1.0.0",
        feature_code="real.github.mcp",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["real_github_mcp_regression"],
        revocation_reasons=["real_github_mcp_disabled"],
        server_configs=[],
    )
    adapter.attach_runtime(
        client_factory=lambda _config: OfficialMcpSdkTransportClient(),
        transcript_store=transcript_store,
        cognitive_registry=CognitiveToolRegistry(transcript_store=transcript_store),
        execution_registry=ExecutionDomainRegistry(),
        auth_service=auth_service,
    )
    acceptance_app.state.mcp_service = McpIntegrationService(adapter=adapter, auth_service=auth_service)


def test_real_github_mcp_api_key_registers_and_query_matches_business_result(
    request: pytest.FixtureRequest,
) -> None:
    case = _load_real_github_case()

    acceptance_app: FastAPI = request.getfixturevalue("acceptance_app")
    tmp_path = request.getfixturevalue("tmp_path")
    auth_service = AgentAuthService(
        AgentCredentialVault(
            DatabaseConnection(f"{tmp_path}/github-auth.sqlite3"),
            master_key="real-github-mcp-master-key",
        )
    )
    original_auth_service = acceptance_app.state.agent_coordination_service.auth_service
    original_mcp_service = acceptance_app.state.mcp_service
    acceptance_app.state.agent_coordination_service.auth_service = auth_service
    _install_real_github_mcp_service(acceptance_app, auth_service)

    suffix = uuid4().hex[:8]
    server_id = f"real-github-{suffix}"
    credential_id = f"real-github-cred-{suffix}"
    api_key = str(case["api_key"])
    query_tool = str(case["query_tool"])
    context = {"suffix": suffix, "server_id": server_id}
    query_arguments = _render_placeholders(case["query_arguments"], context)
    query_assertions = _render_placeholders(case["query_assertions"], context)
    env_headers = _render_placeholders(
        case.get("headers", {}),
        context,
    )
    assert isinstance(env_headers, dict), "ZENTEX_REAL_GITHUB_MCP_HEADERS_JSON must be a JSON object"

    try:
        with live_http_server(acceptance_app) as base_url:
            register_response = requests.post(
                f"{base_url}/api/web/mcp-servers/register",
                json={
                    "server_id": server_id,
                    "name": "Real GitHub MCP",
                    "description": "Real GitHub MCP API-key registration and strict query test",
                    "protocol_version": str(case.get("protocol_version", "2025-03-26")),
                    "transport_type": str(case.get("transport", "http")),
                    "command": str(case.get("command", DEFAULT_GITHUB_MCP_URL)),
                    "env": env_headers,
                    "scope": ["read"],
                    "auth_mode": "api_key",
                    "auth_config": {
                        "type": "api_key",
                        "credential_ref": credential_id,
                        "inject": {"headers": {"Authorization": "Bearer $auth.api_key"}},
                    },
                    "auth_credential": {
                        "credential_id": credential_id,
                        "credential_type": "api_key",
                        "secret_payload": {"api_key": api_key},
                        "metadata": {"provider": "github", "purpose": "real github mcp api key query"},
                    },
                    "documentation_learning_required": False,
                },
                timeout=60,
            )
            assert register_response.status_code == 200, register_response.text
            registered = register_response.json()
            assert registered["server_id"] == server_id
            assert registered["status"] == "online"
            assert registered["tool_count"] > 0
            tool_names = {tool["tool_name"] for tool in registered["tools"]}
            assert query_tool in tool_names
            assert api_key not in register_response.text

            credentials_response = requests.get(
                f"{base_url}/api/web/integrations/mcp/{server_id}/credentials",
                timeout=30,
            )
            assert credentials_response.status_code == 200, credentials_response.text
            credentials = credentials_response.json()
            assert len(credentials) == 1
            assert credentials[0]["credential_id"] == credential_id
            assert credentials[0]["credential_type"] == "api_key"
            assert credentials[0]["metadata"]["provider"] == "github"
            assert api_key not in credentials_response.text

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
            assert api_key not in query_response.text

            health_response = requests.get(f"{base_url}/api/web/mcp-servers/{server_id}/health", timeout=30)
            assert health_response.status_code == 200, health_response.text
            health_payload = health_response.json()
            assert health_payload["status"] == "online"
            assert health_payload["healthy"] is True
    finally:
        acceptance_app.state.agent_coordination_service.auth_service = original_auth_service
        acceptance_app.state.mcp_service = original_mcp_service

    audit_payloads = [
        entry.get("payload") or {}
        for entry in acceptance_app.state.transcript_store.entries
        if (entry.get("payload") or {}).get("server_id") == server_id
    ]
    assert any(item.get("status") == "completed" and item.get("tool_name") == query_tool for item in audit_payloads)
