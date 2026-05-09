from __future__ import annotations

import asyncio
import tempfile
from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.agents.invocations import AgentInvocationLedger
from zentex.agents.manager import AgentAsset, AgentStatus, AgentTrustLevel
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest
from zentex.common.database import DatabaseConnection
from zentex.agents.verification import (
    ActiveProbeConfig,
    AgentVerificationMethod,
    AgentVerificationPlan,
    RemoteResultViewConfig,
    RuleAnalysisConfig,
)
from zentex.cli.models import CliToolRegistrationConfig
from zentex.cli.service import get_service as get_cli_service
from zentex.mcp.models import McpServerConfig, McpToolBindingConfig


class _TranscriptStore:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def write_entry(self, **payload) -> None:
        self.entries.append(payload)

    def list_entries(self, **_) -> list[dict]:
        return list(self.entries)


def _custom_http_agent() -> FastAPI:
    app = FastAPI()
    calls: list[dict] = []

    @app.post("/custom-run")
    def custom_run(payload: dict) -> dict:
        calls.append(payload)
        return {
            "state": "done",
            "task_ref": payload.get("task_ref") or payload.get("external_task_ref"),
            "artifact": {"id": payload["artifact_id"], "text": f"result:{payload['prompt']}"},
        }

    @app.get("/result/{artifact_id}")
    def result(artifact_id: str) -> dict:
        return {"state": "done", "artifact_id": artifact_id}

    @app.get("/probe/{artifact_id}")
    def probe(artifact_id: str) -> dict:
        return {"exists": any(item.get("artifact_id") == artifact_id for item in calls)}

    return app


def test_http_json_adapter_uses_custom_endpoint_and_optional_verification(acceptance_app: FastAPI) -> None:
    service = acceptance_app.state.agent_coordination_service
    suffix = uuid4().hex[:8]
    agent_app = _custom_http_agent()

    with live_http_server(agent_app) as agent_url:
        asset = asyncio.run(
            service.register_agent(
                AgentRegistrationRequest(
                    name=f"http-json-{suffix}",
                    agent_name="HTTP JSON Agent",
                    version="1.0.0",
                    function_description="custom path agent",
                    endpoint=agent_url,
                    auth_token=None,
                    role_tag="http",
                    scope=["http-json"],
                    adapter_type="http_json",
                    adapter_config={
                        "path": "/custom-run",
                        "method": "POST",
                        "body_template": {
                            "prompt": "$payload.prompt",
                            "artifact_id": "$payload.artifact_id",
                            "task_ref": "$invocation.external_task_ref",
                        },
                        "response_mapping": {
                            "status": "$response.state",
                            "task_ref": "$response.task_ref",
                            "content": "$response.artifact.text",
                            "artifact_id": "$response.artifact.id",
                        },
                    },
                    service_hooks=["invoke", "result_view", "active_probe"],
                )
            )
        )
        assert asset.service_hooks == ["invoke", "result_view", "active_probe"]
        assert asset.protocol_capabilities == ["invoke", "result_view", "active_probe"]

        result = asyncio.run(
            service.dispatch_task(
                asset.agent_id,
                {"prompt": "chapter", "artifact_id": f"artifact-{suffix}"},
                AgentVerificationPlan(
                    methods=[
                        AgentVerificationMethod.REMOTE_RESULT_VIEW,
                        AgentVerificationMethod.ACTIVE_PROBE,
                        AgentVerificationMethod.RULE_ANALYSIS,
                    ],
                    remote_result_view=RemoteResultViewConfig(
                        url=f"{agent_url}/result/artifact-{suffix}",
                        expected_json_path="state",
                        expected_equals="done",
                    ),
                    active_probes=[
                        ActiveProbeConfig(
                            name="artifact_exists",
                            url=f"{agent_url}/probe/artifact-{suffix}",
                            expected_json_path="exists",
                            expected_equals=True,
                        )
                    ],
                    rule_analysis=RuleAnalysisConfig(
                        equals={"normalized_result.status": "done"},
                        non_empty_paths=["normalized_result.content"],
                    ),
                ),
            )
        )

    assert result.is_ok
    assert result.data["external_task_ref"].startswith("ztx_taskref_")
    assert result.data["normalized_result"]["task_ref"] == result.data["external_task_ref"]
    assert result.data["adapter_metadata"]["adapter_type"] == "http_json"
    assert result.data["normalized_result"]["content"] == "result:chapter"
    assert result.data["verification"]["overall_status"] == "passed"


def test_http_json_default_injects_external_task_ref_and_persists_ledger() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/agent_invocations.sqlite3"
        ledger = AgentInvocationLedger(DatabaseConnection(db_path))
        service = AgentCoordinationService(invocation_ledger=ledger)
        suffix = uuid4().hex[:8]
        agent_app = FastAPI()

        @agent_app.post("/run")
        def run(payload: dict) -> dict:
            return {"state": "done", "received": payload}

        with live_http_server(agent_app) as agent_url:
            asset = asyncio.run(
                service.register_agent(
                    AgentRegistrationRequest(
                        name=f"default-ref-{suffix}",
                        agent_name="Default Ref Agent",
                        version="1.0.0",
                        function_description="default task ref injection",
                        endpoint=agent_url,
                        auth_token=None,
                        role_tag="http",
                        scope=["http-json"],
                        adapter_type="http_json",
                        adapter_config={
                            "path": "/run",
                            "response_mapping": {
                                "status": "$response.state",
                                "external_task_ref": "$response.received.external_task_ref",
                                "task_ref": "$response.received.task_ref",
                            },
                        },
                        service_hooks=["invoke"],
                    )
                )
            )
            result = asyncio.run(
                service.dispatch_task(
                    asset.agent_id,
                    {"prompt": "draft"},
                    zentex_task_id=f"zentex-task-{suffix}",
                )
            )

        assert result.is_ok
        external_task_ref = result.data["external_task_ref"]
        assert result.data["normalized_result"]["external_task_ref"] == external_task_ref
        assert result.data["normalized_result"]["task_ref"] == external_task_ref
        record = ledger.get_by_external_task_ref(external_task_ref)
        assert record is not None
        assert record.agent_id == asset.agent_id
        assert record.zentex_task_id == f"zentex-task-{suffix}"
        assert record.status == "completed"
        assert record.normalized_result["external_task_ref"] == external_task_ref
        reloaded_service = AgentCoordinationService(
            invocation_ledger=AgentInvocationLedger(DatabaseConnection(db_path))
        )
        reloaded = reloaded_service.get_invocation_by_external_task_ref(external_task_ref)
        assert reloaded is not None
        assert reloaded.request_payload["prompt"] == "draft"
        assert reloaded.normalized_result["task_ref"] == external_task_ref


def test_registration_health_probe_failure_does_not_block_http_dispatch() -> None:
    service = AgentCoordinationService()
    agent_app = _custom_http_agent()
    suffix = uuid4().hex[:8]

    with live_http_server(agent_app) as agent_url:
        asset = asyncio.run(
            service.register_agent(
                AgentRegistrationRequest(
                    name=f"health-fail-{suffix}",
                    agent_name="Health Optional Agent",
                    version="1.0.0",
                    function_description="health probe failure must not block registration",
                    endpoint=agent_url,
                    auth_token=None,
                    role_tag="http",
                    scope=["http-json"],
                    adapter_type="http_json",
                    adapter_config={
                        "path": "/custom-run",
                        "body_template": {"prompt": "$payload.prompt", "artifact_id": "$payload.artifact_id"},
                        "health_probe": {"path": "/missing-health", "expected_status": 200},
                    },
                    protocol_capabilities=["invoke", "health_probe"],
                )
            )
        )
        assert asset.service_hooks == ["invoke", "health_probe"]
        response = asyncio.run(service.dispatch_task(asset.agent_id, {"prompt": "x", "artifact_id": suffix}))

    assert asset.status == AgentStatus.OFFLINE
    assert response.is_ok
    assert response.data["status"] == "completed"


def test_agents_api_dispatches_http_json_adapter_without_zentex_execute_endpoint(acceptance_app: FastAPI) -> None:
    suffix = uuid4().hex[:8]
    agent_app = _custom_http_agent()

    with live_http_server(agent_app) as agent_url, live_http_server(acceptance_app) as base_url:
        register_response = requests.post(
            f"{base_url}/api/web/agents/register",
            json={
                "name": f"api-http-{suffix}",
                "agent_name": "API HTTP Adapter",
                "version": "1.0.0",
                "function_description": "API registered custom adapter",
                "endpoint": agent_url,
                "role_tag": "http",
                "scope": ["http-json"],
                "adapter_type": "http_json",
                "adapter_config": {
                    "path": "/custom-run",
                    "body_template": {"prompt": "$payload.prompt", "artifact_id": "$payload.artifact_id"},
                    "response_mapping": {"status": "$response.state", "artifact_id": "$response.artifact.id"},
                },
                "service_hooks": ["invoke"],
            },
            timeout=10,
        )
        assert register_response.status_code == 200, register_response.text
        registered = register_response.json()
        assert registered["service_hooks"] == ["invoke"]
        agent_id = registered["agent_id"]

        dispatch_response = requests.post(
            f"{base_url}/api/web/agents/{agent_id}/dispatch",
            json={"task_payload": {"prompt": "api", "artifact_id": f"api-artifact-{suffix}"}},
            timeout=10,
        )

    assert dispatch_response.status_code == 200, dispatch_response.text
    payload = dispatch_response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["status"] == "completed"
    assert payload["data"]["external_task_ref"].startswith("ztx_taskref_")
    assert payload["data"]["normalized_result"]["artifact_id"] == f"api-artifact-{suffix}"


def test_cli_mcp_and_webhook_adapters_execute_through_existing_services(acceptance_app: FastAPI) -> None:
    service = acceptance_app.state.agent_coordination_service
    suffix = uuid4().hex[:8]

    cli_service = get_cli_service(transcript_store=_TranscriptStore())
    cli_register = cli_service.register_tool(
        CliToolRegistrationConfig(
            tool_name=f"echo-{suffix}",
            command_executable="/bin/echo",
            command_args=[],
            description="echo for agent adapter",
        )
    )
    assert cli_register.is_ok

    cli_asset = AgentAsset(
        agent_id=f"cli-{suffix}",
        name=f"cli-{suffix}",
        agent_name="CLI Agent Adapter",
        version="1.0.0",
        function_description="CLI adapter asset",
        endpoint="cli://echo",
        auth_token=None,
        role_tag="cli",
        trust_level=AgentTrustLevel.TRUSTED,
        status=AgentStatus.IDLE,
        scope=["cli"],
        adapter_type="cli",
        adapter_config={
            "tool_name": f"echo-{suffix}",
            "arguments": ["$payload.message", "$invocation.external_task_ref"],
            "response_mapping": {"stdout": "$response.stdout", "exit_code": "$response.exit_code"},
        },
        service_hooks=["invoke"],
    )
    service.manager.add_asset(cli_asset)
    cli_response = asyncio.run(
        service.dispatch_task(cli_asset.agent_id, {"message": "hello-cli"}, cli_service=cli_service)
    )
    assert cli_response.is_ok
    assert cli_response.data["external_task_ref"] in cli_response.data["normalized_result"]["stdout"]
    assert "hello-cli" in cli_response.data["normalized_result"]["stdout"]

    mcp_service = acceptance_app.state.mcp_service
    mcp_service.register_server(
        McpServerConfig(
            server_id=f"mcp-{suffix}",
            transport_type="stdio",
            command="fake-mcp",
            tool_bindings=[
                McpToolBindingConfig(tool_name="inspect", domain="cognitive"),
            ],
        )
    )
    mcp_asset = AgentAsset(
        agent_id=f"mcp-agent-{suffix}",
        name=f"mcp-agent-{suffix}",
        agent_name="MCP Agent Adapter",
        version="1.0.0",
        function_description="MCP adapter asset",
        endpoint="mcp://inspect",
        auth_token=None,
        role_tag="mcp",
        trust_level=AgentTrustLevel.TRUSTED,
        status=AgentStatus.IDLE,
        scope=["mcp"],
        adapter_type="mcp",
        adapter_config={
            "server_id": f"mcp-{suffix}",
            "tool_name": "inspect",
            "arguments": {"query": "$payload.query", "task_ref": "$invocation.external_task_ref"},
            "response_mapping": {
                "status": "$response.status",
                "summary": "$response.data.summary",
                "task_ref": "$response.data.arguments.task_ref",
            },
        },
        service_hooks=["invoke"],
    )
    service.manager.add_asset(mcp_asset)
    mcp_response = asyncio.run(
        service.dispatch_task(mcp_asset.agent_id, {"query": "agent"}, mcp_service=mcp_service)
    )
    assert mcp_response.is_ok
    assert mcp_response.data["normalized_result"]["status"] == "completed"
    assert mcp_response.data["normalized_result"]["task_ref"] == mcp_response.data["external_task_ref"]
    assert "inspect ok" in mcp_response.data["normalized_result"]["summary"]

    webhook_app = FastAPI()

    @webhook_app.post("/hook")
    def hook(payload: dict) -> dict:
        return {"accepted": True, "received": payload}

    with live_http_server(webhook_app) as webhook_url:
        webhook_asset = AgentAsset(
            agent_id=f"webhook-{suffix}",
            name=f"webhook-{suffix}",
            agent_name="Webhook Adapter",
            version="1.0.0",
            function_description="Webhook adapter asset",
            endpoint=webhook_url,
            auth_token=None,
            role_tag="webhook",
            trust_level=AgentTrustLevel.TRUSTED,
            status=AgentStatus.IDLE,
            scope=["webhook"],
            adapter_type="webhook",
            adapter_config={
                "path": "/hook",
                "body_template": {"event": "$payload.event", "external_task_ref": "$invocation.external_task_ref"},
                "response_mapping": {
                    "accepted": "$response.accepted",
                    "event": "$response.received.event",
                    "external_task_ref": "$response.received.external_task_ref",
                },
            },
            service_hooks=["invoke"],
        )
        service.manager.add_asset(webhook_asset)
        webhook_response = asyncio.run(service.dispatch_task(webhook_asset.agent_id, {"event": "done"}))

    assert webhook_response.is_ok
    assert webhook_response.data["status"] == "submitted"
    assert webhook_response.data["normalized_result"] == {
        "accepted": True,
        "event": "done",
        "external_task_ref": webhook_response.data["external_task_ref"],
    }


def test_callback_updates_invocation_by_external_task_ref_without_trusting_agent_id(acceptance_app: FastAPI) -> None:
    suffix = uuid4().hex[:8]
    agent_app = FastAPI()

    @agent_app.post("/run")
    def run(payload: dict) -> dict:
        return {
            "state": "submitted",
            "external_task_ref": payload["external_task_ref"],
            "callback_url": payload["callback_url"],
            "callback_token": payload["callback_token"],
        }

    with live_http_server(agent_app) as agent_url, live_http_server(acceptance_app) as base_url:
        register_response = requests.post(
            f"{base_url}/api/web/agents/register",
            json={
                "name": f"callback-agent-{suffix}",
                "agent_name": "Callback Agent",
                "version": "1.0.0",
                "function_description": "callback result agent",
                "endpoint": agent_url,
                "role_tag": "http",
                "scope": ["http-json"],
                "adapter_type": "http_json",
                "adapter_config": {
                    "path": "/run",
                    "enable_callback": True,
                    "callback_base_url": base_url,
                    "response_mapping": {
                        "status": "$response.state",
                        "external_task_ref": "$response.external_task_ref",
                        "callback_url": "$response.callback_url",
                        "callback_token": "$response.callback_token",
                    },
                },
                "service_hooks": ["invoke", "callback_result"],
            },
            timeout=10,
        )
        assert register_response.status_code == 200, register_response.text
        agent_id = register_response.json()["agent_id"]

        dispatch_response = requests.post(
            f"{base_url}/api/web/agents/{agent_id}/dispatch",
            json={"task_payload": {"prompt": "async"}, "zentex_task_id": f"ztask-{suffix}"},
            timeout=10,
        )
        assert dispatch_response.status_code == 200, dispatch_response.text
        dispatch_payload = dispatch_response.json()["data"]
        external_task_ref = dispatch_payload["external_task_ref"]
        callback_token = dispatch_payload["normalized_result"]["callback_token"]

        bad_callback = requests.post(
            f"{base_url}/api/web/agents/callbacks/{external_task_ref}",
            json={"callback_token": "wrong", "status": "completed"},
            timeout=10,
        )
        assert bad_callback.status_code == 403

        callback_response = requests.post(
            f"{base_url}/api/web/agents/callbacks/{external_task_ref}",
            json={
                "callback_token": callback_token,
                "status": "waiting_external_human_review",
                "normalized_result": {"agent_id": "spoofed-agent", "review_id": f"review-{suffix}"},
                "raw_response": {"agent_id": "spoofed-agent", "state": "review"},
            },
            timeout=10,
        )
        assert callback_response.status_code == 200, callback_response.text

        ledger_response = requests.get(
            f"{base_url}/api/web/agents/invocations/{external_task_ref}",
            timeout=10,
        )
        task_invocations = requests.get(
            f"{base_url}/api/web/agents/tasks/ztask-{suffix}/invocations",
            timeout=10,
        )

    assert ledger_response.status_code == 200, ledger_response.text
    record = ledger_response.json()
    assert record["agent_id"] == agent_id
    assert record["status"] == "waiting_external_human_review"
    assert record["normalized_result"]["agent_id"] == "spoofed-agent"
    assert task_invocations.status_code == 200, task_invocations.text
    assert task_invocations.json()[0]["external_task_ref"] == external_task_ref
