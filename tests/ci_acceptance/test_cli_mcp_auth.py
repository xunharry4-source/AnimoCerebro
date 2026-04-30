from __future__ import annotations

import json
import hashlib
import sys
import tempfile
from uuid import uuid4

import requests
from fastapi import FastAPI, Header, Request

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.agents.auth import AgentAuthService, AgentCredentialVault
from zentex.cli.adapter import create_cli_adapter_plugin
from zentex.cli.models import CliToolRegistrationConfig
from zentex.cli.service import CliIntegrationService
from zentex.common.database import DatabaseConnection
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.http_transport import HttpJsonMcpTransportClient
from zentex.mcp.models import McpServerConfig, McpToolBindingConfig
from zentex.mcp.service import McpIntegrationService
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry, ExecutionDomainRegistry


class _TranscriptStore:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def write_entry(self, **payload) -> None:
        self.entries.append(payload)


def _auth_service(db_path: str) -> AgentAuthService:
    return AgentAuthService(AgentCredentialVault(DatabaseConnection(db_path), master_key="cli-mcp-auth-master-key"))


def _cli_service(auth_service: AgentAuthService, registry_path: str) -> CliIntegrationService:
    transcript_store = _TranscriptStore()
    adapter = create_cli_adapter_plugin(transcript_store=transcript_store)
    return CliIntegrationService(
        adapter=adapter,
        transcript_store=transcript_store,
        documentation_learning_service=None,
        auth_service=auth_service,
        registry_path=registry_path,
    )


def _mcp_service(auth_service: AgentAuthService) -> McpIntegrationService:
    transcript_store = _TranscriptStore()
    adapter = McpAdapterPlugin(
        plugin_id="mcp-auth-adapter",
        version="1.0.0",
        feature_code="auth.mcp",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["auth_regression"],
        revocation_reasons=["auth_disabled"],
        server_configs=[],
    )
    adapter.attach_runtime(
        client_factory=lambda _config: HttpJsonMcpTransportClient(timeout_seconds=1.0),
        transcript_store=transcript_store,
        cognitive_registry=CognitiveToolRegistry(transcript_store=transcript_store),
        execution_registry=ExecutionDomainRegistry(),
        auth_service=auth_service,
    )
    return McpIntegrationService(adapter=adapter, auth_service=auth_service)

def test_cli_api_key_defaults_to_env_and_redacts_output() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        auth_service = _auth_service(f"{tmpdir}/auth.sqlite3")
        service = _cli_service(auth_service, f"{tmpdir}/cli_tools.json")
        suffix = uuid4().hex[:8]
        tool_name = f"cli-auth-{suffix}"
        expected_hash = hashlib.sha256(b"cli-secret-key").hexdigest()
        code = (
            "import hashlib, json, os; "
            f"print(json.dumps({{'accepted': hashlib.sha256((os.environ.get('ZENTEX_CLI_API_KEY') or '').encode()).hexdigest() == '{expected_hash}', "
            "'token': os.environ.get('ZENTEX_CLI_API_KEY')}))"
        )
        register = service.register_tool(
            CliToolRegistrationConfig(
                tool_name=tool_name,
                command_executable=sys.executable,
                command_args=["-c", code],
                description="auth env test",
                read_only_flag=False,
                documentation_learning_required=False,
                auth_config={"type": "api_key", "credential_ref": f"cli-cred-{suffix}"},
            )
        )
        assert register.is_ok, register.message
        auth_service.store_credential(
            agent_id=f"cli:{tool_name}",
            owner_type="cli",
            owner_id=tool_name,
            credential_type="api_key",
            credential_id=f"cli-cred-{suffix}",
            secret_payload={"api_key": "cli-secret-key"},
        )

        result = service.test_call(tool_name)

        assert result.is_ok
        payload = json.loads(result.data.stdout)
        assert payload["accepted"] is True
        assert payload["token"] == "[REDACTED]"
        assert "cli-secret-key" not in str(result.data.model_dump(mode="json"))


def test_cli_login_flow_runs_before_tool_call_and_injects_token_env() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        auth_service = _auth_service(f"{tmpdir}/auth.sqlite3")
        service = _cli_service(auth_service, f"{tmpdir}/cli_tools.json")
        suffix = uuid4().hex[:8]
        tool_name = f"cli-login-{suffix}"
        expected_hash = hashlib.sha256(b"cli-login-token").hexdigest()
        tool_code = (
            "import hashlib, json, os; "
            f"print(json.dumps({{'accepted': hashlib.sha256((os.environ.get('ZENTEX_CLI_ACCESS_TOKEN') or '').encode()).hexdigest() == '{expected_hash}'}}))"
        )
        login_code = "import json; print(json.dumps({'access_token': 'cli-login-token', 'expires_in': 3600}))"
        register = service.register_tool(
            CliToolRegistrationConfig(
                tool_name=tool_name,
                command_executable=sys.executable,
                command_args=["-c", tool_code],
                description="auth login test",
                read_only_flag=False,
                documentation_learning_required=False,
                auth_config={
                    "type": "login_flow",
                    "credential_ref": f"cli-login-cred-{suffix}",
                    "login_command": {
                        "command_executable": sys.executable,
                        "args": ["-c", login_code],
                    },
                },
            )
        )
        assert register.is_ok, register.message
        auth_service.store_credential(
            agent_id=f"cli:{tool_name}",
            owner_type="cli",
            owner_id=tool_name,
            credential_type="login_flow",
            credential_id=f"cli-login-cred-{suffix}",
            secret_payload={"username": "local"},
        )

        result = service.test_call(tool_name)

        assert result.is_ok
        assert json.loads(result.data.stdout)["accepted"] is True
        assert "cli-login-token" not in str(result.data.model_dump(mode="json"))


def test_cli_rejects_direct_secret_in_env() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        auth_service = _auth_service(f"{tmpdir}/auth.sqlite3")
        service = _cli_service(auth_service, f"{tmpdir}/cli_tools.json")
        response = service.register_tool(
            CliToolRegistrationConfig(
                tool_name=f"cli-bad-{uuid4().hex[:8]}",
                command_executable=sys.executable,
                command_args=["--version"],
                description="bad secret",
                read_only_flag=False,
                documentation_learning_required=False,
                env={"ZENTEX_CLI_API_KEY": "plain-secret"},
            )
        )
        assert response.is_error
        assert "credential vault" in response.message


def test_cli_api_key_auth_api_uses_requests_and_verifies_query_after_mutations(acceptance_app: FastAPI) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        auth_service = _auth_service(f"{tmpdir}/auth.sqlite3")
        original_auth_service = acceptance_app.state.agent_coordination_service.auth_service
        acceptance_app.state.agent_coordination_service.auth_service = auth_service
        acceptance_app.state.cli_service._adapter.attach_auth_service(auth_service)
        suffix = uuid4().hex[:8]
        tool_name = f"cli-api-auth-{suffix}"
        credential_id = f"cli-api-cred-{suffix}"
        api_key = f"cli-api-secret-{suffix}"
        expected_hash = hashlib.sha256(api_key.encode()).hexdigest()
        code = (
            "import hashlib, json, os; "
            "token = os.environ.get('ZENTEX_CLI_API_KEY') or ''; "
            "print(json.dumps({"
            f"'accepted': hashlib.sha256(token.encode()).hexdigest() == '{expected_hash}', "
            "'token': token"
            "}))"
        )

        with live_http_server(acceptance_app) as base_url:
            credential_response = requests.post(
                f"{base_url}/api/web/integrations/cli/{tool_name}/credentials",
                json={
                    "credential_id": credential_id,
                    "credential_type": "api_key",
                    "secret_payload": {"api_key": api_key},
                    "metadata": {"purpose": "cli auth api regression", "suffix": suffix},
                },
                timeout=10,
            )
            assert credential_response.status_code == 200, credential_response.text
            assert credential_response.json()["credential_id"] == credential_id
            assert credential_response.json()["owner_type"] == "cli"
            assert credential_response.json()["owner_id"] == tool_name
            assert "secret_payload" not in credential_response.json()
            assert api_key not in credential_response.text

            credentials_response = requests.get(
                f"{base_url}/api/web/integrations/cli/{tool_name}/credentials",
                timeout=10,
            )
            assert credentials_response.status_code == 200, credentials_response.text
            credentials_payload = credentials_response.json()
            assert len(credentials_payload) == 1
            assert credentials_payload[0]["credential_id"] == credential_id
            assert credentials_payload[0]["credential_type"] == "api_key"
            assert credentials_payload[0]["owner_type"] == "cli"
            assert credentials_payload[0]["owner_id"] == tool_name
            assert credentials_payload[0]["metadata"] == {"purpose": "cli auth api regression", "suffix": suffix}
            assert api_key not in credentials_response.text

            auth_test_response = requests.post(
                f"{base_url}/api/web/integrations/cli/{tool_name}/auth/test",
                json={"auth_config": {"type": "api_key", "credential_ref": credential_id}},
                timeout=10,
            )
            assert auth_test_response.status_code == 200, auth_test_response.text
            auth_test_payload = auth_test_response.json()
            assert auth_test_payload["status"] == "ok"
            assert auth_test_payload["data"]["auth_type"] == "api_key"
            assert auth_test_payload["data"]["credential_ref"] == credential_id
            assert auth_test_payload["data"]["env"] == {"ZENTEX_CLI_API_KEY": "[REDACTED]"}
            assert api_key not in auth_test_response.text

            register_response = requests.post(
                f"{base_url}/api/web/cli-tools/register",
                json={
                    "tool_name": tool_name,
                    "command_executable": sys.executable,
                    "command_args": ["-c", code],
                    "description": "CLI API auth regression",
                    "read_only_flag": True,
                    "documentation_learning_required": False,
                    "auth_config": {"type": "api_key", "credential_ref": credential_id},
                },
                timeout=10,
            )
            assert register_response.status_code == 200, register_response.text
            assert register_response.json()["command_name"] == tool_name
            assert register_response.json()["status"] == "active"
            assert api_key not in register_response.text

            tools_response = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
            assert tools_response.status_code == 200, tools_response.text
            assert any(item["command_name"] == tool_name and item["status"] == "active" for item in tools_response.json())

            call_response = requests.post(
                f"{base_url}/api/web/cli-tools/{tool_name}/test-call",
                json={"timeout_seconds": 5},
                timeout=10,
            )
            assert call_response.status_code == 200, call_response.text
            call_payload = call_response.json()
            assert call_payload["status"] == "success"
            assert call_payload["exit_code"] == 0
            stdout_payload = json.loads(call_payload["stdout"])
            assert stdout_payload == {"accepted": True, "token": "[REDACTED]"}
            assert api_key not in call_response.text

            delete_credential_response = requests.delete(
                f"{base_url}/api/web/integrations/cli/{tool_name}/credentials/{credential_id}",
                timeout=10,
            )
            assert delete_credential_response.status_code == 200, delete_credential_response.text
            assert delete_credential_response.json() == {"success": True}

            credentials_after_delete_response = requests.get(
                f"{base_url}/api/web/integrations/cli/{tool_name}/credentials",
                timeout=10,
            )
            assert credentials_after_delete_response.status_code == 200, credentials_after_delete_response.text
            assert credentials_after_delete_response.json() == []

            call_after_delete_response = requests.post(
                f"{base_url}/api/web/cli-tools/{tool_name}/test-call",
                json={"timeout_seconds": 5},
                timeout=10,
            )
            assert call_after_delete_response.status_code == 400, call_after_delete_response.text
            assert "Credential not found" in call_after_delete_response.text
            assert api_key not in call_after_delete_response.text

            delete_tool_response = requests.delete(f"{base_url}/api/web/cli-tools/{tool_name}", timeout=10)
            assert delete_tool_response.status_code == 200, delete_tool_response.text
            assert delete_tool_response.json() == {"success": True, "tool_name": tool_name}
            tools_after_delete_response = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
            assert tools_after_delete_response.status_code == 200, tools_after_delete_response.text
            assert all(item["command_name"] != tool_name for item in tools_after_delete_response.json())
            assert requests.get(f"{base_url}/api/web/cli-tools/{tool_name}/health", timeout=10).status_code == 404
        acceptance_app.state.agent_coordination_service.auth_service = original_auth_service
        acceptance_app.state.cli_service._adapter.attach_auth_service(original_auth_service)


def _mcp_app(expected_header: str = "mcp-secret-key") -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health(x_api_key: str = Header(default="")) -> dict:
        return {"ok": x_api_key == expected_header}

    @app.get("/tools")
    def tools(x_api_key: str = Header(default="")) -> dict:
        assert x_api_key == expected_header
        return {
            "tools": [
                {
                    "tool_name": "inspect",
                    "description": "inspect",
                    "input_schema": {"type": "object"},
                    "mutates_state": False,
                    "read_only_hint": True,
                }
            ]
        }

    @app.post("/tools/inspect/call")
    async def call(request: Request, x_api_key: str = Header(default="")) -> dict:
        payload = await request.json()
        return {"accepted": x_api_key == expected_header, "arguments": payload.get("arguments", {})}

    return app


def test_mcp_http_api_key_injects_headers() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        auth_service = _auth_service(f"{tmpdir}/auth.sqlite3")
        service = _mcp_service(auth_service)
        suffix = uuid4().hex[:8]
        server_id = f"mcp-auth-{suffix}"
        with live_http_server(_mcp_app()) as base_url:
            auth_service.store_credential(
                agent_id=f"mcp:{server_id}",
                owner_type="mcp",
                owner_id=server_id,
                credential_type="api_key",
                credential_id=f"mcp-cred-{suffix}",
                secret_payload={"api_key": "mcp-secret-key"},
            )
            state = service.register_server(
                McpServerConfig(
                    server_id=server_id,
                    transport_type="http",
                    command=base_url,
                    auth_config={
                        "type": "api_key",
                        "credential_ref": f"mcp-cred-{suffix}",
                        "key_name": "X-API-Key",
                    },
                    tool_bindings=[McpToolBindingConfig(tool_name="inspect", domain="cognitive")],
                    documentation_learning_required=False,
                )
            )
            result = service.test_call(server_id, tool_name="inspect", arguments={"query": "x"})

        assert state.status == "online"
        assert result["status"] == "completed"
        assert result["data"]["accepted"] is True
        assert "mcp-secret-key" not in str(result)


def test_mcp_http_login_flow_injects_token_header() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        auth_service = _auth_service(f"{tmpdir}/auth.sqlite3")
        service = _mcp_service(auth_service)
        suffix = uuid4().hex[:8]
        server_id = f"mcp-login-{suffix}"
        app = _mcp_app(expected_header="mcp-login-token")

        @app.post("/login")
        def login(payload: dict) -> dict:
            assert payload == {"client": "mcp"}
            return {"access_token": "mcp-login-token", "expires_in": 3600}

        with live_http_server(app) as base_url:
            auth_service.store_credential(
                agent_id=f"mcp:{server_id}",
                owner_type="mcp",
                owner_id=server_id,
                credential_type="login_flow",
                credential_id=f"mcp-login-cred-{suffix}",
                secret_payload={"client": "mcp"},
            )
            state = service.register_server(
                McpServerConfig(
                    server_id=server_id,
                    transport_type="http",
                    command=base_url,
                    auth_config={
                        "type": "login_flow",
                        "credential_ref": f"mcp-login-cred-{suffix}",
                        "login_http": {
                            "path": "/login",
                            "body_template": {"client": "$credential.client"},
                        },
                        "inject": {"headers": {"X-API-Key": "$auth.access_token"}},
                    },
                    tool_bindings=[McpToolBindingConfig(tool_name="inspect", domain="cognitive")],
                    documentation_learning_required=False,
                )
            )
            result = service.test_call(server_id, tool_name="inspect", arguments={"query": "x"})

        assert state.status == "online"
        assert result["status"] == "completed"
        assert result["data"]["accepted"] is True
        assert "mcp-login-token" not in str(result)
