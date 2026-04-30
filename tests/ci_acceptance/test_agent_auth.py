from __future__ import annotations

import asyncio
import tempfile
from urllib.parse import parse_qs
from uuid import uuid4

import requests
from fastapi import FastAPI, Header, Query, Request, Response

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.agents.auth import AgentAuthService, AgentCredentialVault
from zentex.agents.invocations import AgentInvocationLedger
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest
from zentex.common.database import DatabaseConnection


def _service(db_path: str) -> AgentCoordinationService:
    db = DatabaseConnection(db_path)
    return AgentCoordinationService(
        invocation_ledger=AgentInvocationLedger(db),
        auth_service=AgentAuthService(AgentCredentialVault(db, master_key="test-agent-auth-master-key")),
    )


def test_bearer_token_dispatch_uses_encrypted_credential_and_redacts_ledger() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(f"{tmpdir}/agents.sqlite3")
        suffix = uuid4().hex[:8]
        credential_ref = f"bearer-{suffix}"
        agent_app = FastAPI()

        @agent_app.post("/run")
        def run(request: Request) -> dict:
            assert request.headers.get("authorization") == "Bearer secret-bearer-token"
            return {"ok": True, "received_authorization": request.headers.get("authorization")}

        with live_http_server(agent_app) as agent_url:
            asset = asyncio.run(
                service.register_agent(
                    AgentRegistrationRequest(
                        name=f"bearer-{suffix}",
                        agent_name="Bearer Agent",
                        version="1.0.0",
                        function_description="requires bearer token",
                        endpoint=agent_url,
                        role_tag="http",
                        scope=["http-json"],
                        adapter_type="http_json",
                        adapter_config={"path": "/run"},
                        auth_config={
                            "type": "bearer_token",
                            "credential_ref": credential_ref,
                            "inject": {"headers": {"Authorization": "Bearer $auth.access_token"}},
                        },
                        service_hooks=["invoke"],
                    )
                )
            )
            assert asset.auth_config["inject"]["headers"]["Authorization"] == "Bearer $auth.access_token"
            credential = service.store_agent_credential(
                asset.agent_id,
                credential_type="bearer_token",
                credential_id=credential_ref,
                secret_payload={"token": "secret-bearer-token"},
            )
            result = asyncio.run(service.dispatch_task(asset.agent_id, {"prompt": "draft"}))

        assert credential.credential_id == credential_ref
        assert result.is_ok
        assert service.auth_service.vault.get_metadata(credential_ref).last_auth_status == "resolved"
        listed = service.list_agent_credentials(asset.agent_id)
        assert listed[0].model_dump(mode="json").get("secret_payload") is None
        record = service.get_invocation_by_external_task_ref(result.data["external_task_ref"])
        assert record is not None
        assert record.raw_response["received_authorization"] == "[REDACTED]"
        assert "secret-bearer-token" not in str(record.model_dump(mode="json"))


def test_api_key_header_and_query_injection() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(f"{tmpdir}/agents.sqlite3")
        suffix = uuid4().hex[:8]
        agent_app = FastAPI()

        @agent_app.post("/header")
        def header_auth(x_api_key: str = Header(default="")) -> dict:
            return {"accepted": x_api_key == "secret-api-key"}

        @agent_app.post("/query")
        def query_auth(api_key: str = Query(default="")) -> dict:
            return {"accepted": api_key == "secret-api-key"}

        with live_http_server(agent_app) as agent_url:
            header_asset = asyncio.run(
                service.register_agent(
                    AgentRegistrationRequest(
                        name=f"api-header-{suffix}",
                        agent_name="API Header Agent",
                        version="1.0.0",
                        function_description="api key header",
                        endpoint=agent_url,
                        role_tag="http",
                        scope=["http-json"],
                        adapter_type="http_json",
                        adapter_config={"path": "/header", "response_mapping": {"accepted": "$response.accepted"}},
                        auth_config={
                            "type": "api_key",
                            "credential_ref": f"api-header-{suffix}",
                            "location": "headers",
                            "key_name": "X-API-Key",
                        },
                    )
                )
            )
            service.store_agent_credential(
                header_asset.agent_id,
                credential_type="api_key",
                credential_id=f"api-header-{suffix}",
                secret_payload={"api_key": "secret-api-key"},
            )
            query_asset = asyncio.run(
                service.register_agent(
                    AgentRegistrationRequest(
                        name=f"api-query-{suffix}",
                        agent_name="API Query Agent",
                        version="1.0.0",
                        function_description="api key query",
                        endpoint=agent_url,
                        role_tag="http",
                        scope=["http-json"],
                        adapter_type="http_json",
                        adapter_config={"path": "/query", "response_mapping": {"accepted": "$response.accepted"}},
                        auth_config={
                            "type": "api_key",
                            "credential_ref": f"api-query-{suffix}",
                            "location": "query",
                            "key_name": "api_key",
                        },
                    )
                )
            )
            service.store_agent_credential(
                query_asset.agent_id,
                credential_type="api_key",
                credential_id=f"api-query-{suffix}",
                secret_payload={"api_key": "secret-api-key"},
            )
            header_result = asyncio.run(service.dispatch_task(header_asset.agent_id, {}))
            query_result = asyncio.run(service.dispatch_task(query_asset.agent_id, {}))

        assert header_result.is_ok
        assert header_result.data["normalized_result"]["accepted"] is True
        assert query_result.is_ok
        assert query_result.data["normalized_result"]["accepted"] is True


def test_basic_auth_dispatch() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(f"{tmpdir}/agents.sqlite3")
        suffix = uuid4().hex[:8]
        credential_ref = f"basic-{suffix}"
        agent_app = FastAPI()

        @agent_app.post("/run")
        def run(request: Request) -> dict:
            return {"accepted": request.headers.get("authorization") == "Basic dXNlcjpwYXNz"}

        with live_http_server(agent_app) as agent_url:
            asset = asyncio.run(
                service.register_agent(
                    AgentRegistrationRequest(
                        name=f"basic-{suffix}",
                        agent_name="Basic Agent",
                        version="1.0.0",
                        function_description="basic auth",
                        endpoint=agent_url,
                        role_tag="http",
                        scope=["http-json"],
                        adapter_type="http_json",
                        adapter_config={"path": "/run", "response_mapping": {"accepted": "$response.accepted"}},
                        auth_config={"type": "basic", "credential_ref": credential_ref},
                    )
                )
            )
            service.store_agent_credential(
                asset.agent_id,
                credential_type="basic",
                credential_id=credential_ref,
                secret_payload={"username": "user", "password": "pass"},
            )
            result = asyncio.run(service.dispatch_task(asset.agent_id, {}))

        assert result.is_ok
        assert result.data["normalized_result"]["accepted"] is True
        assert "pass" not in str(service.list_agent_credentials(asset.agent_id)[0].model_dump(mode="json"))


def test_login_flow_reauths_once_after_401() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(f"{tmpdir}/agents.sqlite3")
        suffix = uuid4().hex[:8]
        credential_ref = f"login-{suffix}"
        agent_app = FastAPI()
        login_tokens: list[str] = []

        @agent_app.post("/login")
        def login(payload: dict) -> dict:
            assert payload == {"username": "writer", "password": "secret-password"}
            token = "stale-token" if not login_tokens else "fresh-token"
            login_tokens.append(token)
            return {"access_token": token, "expires_in": 3600}

        @agent_app.post("/run")
        def run(request: Request, response: Response) -> dict:
            if request.headers.get("authorization") != "Bearer fresh-token":
                response.status_code = 401
                return {"error": "expired"}
            return {"accepted": True}

        with live_http_server(agent_app) as agent_url:
            asset = asyncio.run(
                service.register_agent(
                    AgentRegistrationRequest(
                        name=f"login-{suffix}",
                        agent_name="Login Agent",
                        version="1.0.0",
                        function_description="login flow",
                        endpoint=agent_url,
                        role_tag="http",
                        scope=["http-json"],
                        adapter_type="http_json",
                        adapter_config={"path": "/run", "response_mapping": {"accepted": "$response.accepted"}},
                        auth_config={
                            "type": "login_flow",
                            "credential_ref": credential_ref,
                            "login_request": {
                                "path": "/login",
                                "body_template": {
                                    "username": "$credential.username",
                                    "password": "$credential.password",
                                },
                            },
                        },
                    )
                )
            )
            service.store_agent_credential(
                asset.agent_id,
                credential_type="login_flow",
                credential_id=credential_ref,
                secret_payload={"username": "writer", "password": "secret-password"},
            )
            result = asyncio.run(service.dispatch_task(asset.agent_id, {}))

        assert result.is_ok
        assert result.data["normalized_result"]["accepted"] is True
        assert login_tokens == ["stale-token", "fresh-token"]


def test_oauth2_client_credentials_dispatch() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = _service(f"{tmpdir}/agents.sqlite3")
        suffix = uuid4().hex[:8]
        credential_ref = f"oauth-{suffix}"
        agent_app = FastAPI()

        @agent_app.post("/oauth/token")
        async def token(request: Request) -> dict:
            form = {key: values[0] for key, values in parse_qs((await request.body()).decode()).items()}
            assert form["grant_type"] == "client_credentials"
            assert form["client_id"] == "client-id"
            assert form["client_secret"] == "client-secret"
            assert form["scope"] == "write read"
            return {"access_token": "oauth-access-token", "expires_in": 3600, "token_type": "Bearer"}

        @agent_app.post("/run")
        def run(request: Request) -> dict:
            return {"accepted": request.headers.get("authorization") == "Bearer oauth-access-token"}

        with live_http_server(agent_app) as agent_url:
            asset = asyncio.run(
                service.register_agent(
                    AgentRegistrationRequest(
                        name=f"oauth-{suffix}",
                        agent_name="OAuth Agent",
                        version="1.0.0",
                        function_description="oauth client credentials",
                        endpoint=agent_url,
                        role_tag="http",
                        scope=["http-json"],
                        adapter_type="http_json",
                        adapter_config={"path": "/run", "response_mapping": {"accepted": "$response.accepted"}},
                        auth_config={
                            "type": "oauth2_client_credentials",
                            "credential_ref": credential_ref,
                            "token_path": "/oauth/token",
                            "scopes": ["write", "read"],
                        },
                    )
                )
            )
            service.store_agent_credential(
                asset.agent_id,
                credential_type="oauth2_client_credentials",
                credential_id=credential_ref,
                secret_payload={"client_id": "client-id", "client_secret": "client-secret"},
            )
            result = asyncio.run(service.dispatch_task(asset.agent_id, {}))

        assert result.is_ok
        assert result.data["normalized_result"]["accepted"] is True
        assert "client-secret" not in str(service.list_agent_credentials(asset.agent_id)[0].model_dump(mode="json"))


def test_credentials_api_stores_metadata_only_and_dispatches(acceptance_app: FastAPI) -> None:
    suffix = uuid4().hex[:8]
    db = DatabaseConnection(f"{tempfile.gettempdir()}/agent-auth-api-{suffix}.sqlite3")
    original_auth_service = acceptance_app.state.agent_coordination_service.auth_service
    acceptance_app.state.agent_coordination_service.auth_service = AgentAuthService(
        AgentCredentialVault(db, master_key="api-route-master-key")
    )
    agent_app = FastAPI()

    @agent_app.post("/run")
    def run(request: Request) -> dict:
        return {"accepted": request.headers.get("authorization") == "Bearer api-route-token"}

    with live_http_server(agent_app) as agent_url, live_http_server(acceptance_app) as base_url:
        register_response = requests.post(
            f"{base_url}/api/web/agents/register",
            json={
                "name": f"auth-api-{suffix}",
                "agent_name": "Auth API Agent",
                "version": "1.0.0",
                "function_description": "credential api",
                "endpoint": agent_url,
                "role_tag": "http",
                "scope": ["http-json"],
                "adapter_type": "http_json",
                "adapter_config": {"path": "/run", "response_mapping": {"accepted": "$response.accepted"}},
                "auth_config": {"type": "bearer_token", "credential_ref": f"api-route-{suffix}"},
            },
            timeout=10,
        )
        assert register_response.status_code == 200, register_response.text
        agent_id = register_response.json()["agent_id"]

        credential_response = requests.post(
            f"{base_url}/api/web/agents/{agent_id}/credentials",
            json={
                "credential_id": f"api-route-{suffix}",
                "credential_type": "bearer_token",
                "secret_payload": {"token": "api-route-token"},
                "metadata": {"purpose": "agent credential route regression", "suffix": suffix},
            },
            timeout=10,
        )
        credentials_response = requests.get(f"{base_url}/api/web/agents/{agent_id}/credentials", timeout=10)
        auth_test_response = requests.post(
            f"{base_url}/api/web/agents/{agent_id}/auth/test",
            json={"force_refresh": True},
            timeout=10,
        )
        list_response = requests.get(f"{base_url}/api/web/agents", timeout=10)
        dispatch_response = requests.post(
            f"{base_url}/api/web/agents/{agent_id}/dispatch",
            json={"task_payload": {"prompt": "api"}},
            timeout=10,
        )
        delete_credential_response = requests.delete(
            f"{base_url}/api/web/agents/{agent_id}/credentials/api-route-{suffix}",
            timeout=10,
        )
        credentials_after_delete_response = requests.get(f"{base_url}/api/web/agents/{agent_id}/credentials", timeout=10)
        auth_test_after_delete_response = requests.post(
            f"{base_url}/api/web/agents/{agent_id}/auth/test",
            json={"force_refresh": True},
            timeout=10,
        )
        delete_credential_again_response = requests.delete(
            f"{base_url}/api/web/agents/{agent_id}/credentials/api-route-{suffix}",
            timeout=10,
        )

    assert credential_response.status_code == 200, credential_response.text
    credential_payload = credential_response.json()
    assert credential_payload["credential_id"] == f"api-route-{suffix}"
    assert credential_payload["owner_type"] == "agent"
    assert credential_payload["owner_id"] == agent_id
    assert credential_payload["metadata"] == {"purpose": "agent credential route regression", "suffix": suffix}
    assert "secret_payload" not in credential_payload
    assert "api-route-token" not in credential_response.text
    assert credentials_response.status_code == 200, credentials_response.text
    credentials_payload = credentials_response.json()
    assert len(credentials_payload) == 1
    assert credentials_payload[0]["credential_id"] == f"api-route-{suffix}"
    assert credentials_payload[0]["credential_type"] == "bearer_token"
    assert credentials_payload[0]["owner_type"] == "agent"
    assert credentials_payload[0]["owner_id"] == agent_id
    assert credentials_payload[0]["metadata"] == {"purpose": "agent credential route regression", "suffix": suffix}
    assert "api-route-token" not in credentials_response.text
    assert auth_test_response.status_code == 200, auth_test_response.text
    auth_test_payload = auth_test_response.json()
    assert auth_test_payload["status"] == "ok"
    assert auth_test_payload["data"]["auth_type"] == "bearer_token"
    assert auth_test_payload["data"]["credential_ref"] == f"api-route-{suffix}"
    assert auth_test_payload["data"]["headers"] == {"Authorization": "[REDACTED]"}
    assert "api-route-token" not in auth_test_response.text
    assert "api-route-token" not in list_response.text
    assert dispatch_response.status_code == 200, dispatch_response.text
    assert dispatch_response.json()["data"]["normalized_result"]["accepted"] is True
    assert "api-route-token" not in dispatch_response.text
    assert delete_credential_response.status_code == 200, delete_credential_response.text
    assert delete_credential_response.json() == {"success": True}
    assert credentials_after_delete_response.status_code == 200, credentials_after_delete_response.text
    assert credentials_after_delete_response.json() == []
    assert auth_test_after_delete_response.status_code == 400, auth_test_after_delete_response.text
    assert "Credential not found" in auth_test_after_delete_response.text
    assert delete_credential_again_response.status_code == 404
    acceptance_app.state.agent_coordination_service.auth_service = original_auth_service
