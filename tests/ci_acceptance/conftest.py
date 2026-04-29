from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zentex.agents.service import get_service as get_agent_service
from zentex.audit.service import get_service as get_audit_service
from zentex.cli.service import get_service as get_cli_service
from zentex.learning.service import get_service as get_learning_service
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.models import McpServerConfig, McpToolDescriptor
from zentex.mcp.service import McpIntegrationService
from zentex.memory.service import get_service as get_memory_service
from zentex.nine_questions.service import NineQuestionService
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry, ExecutionDomainRegistry
from zentex.plugins.service import SystemPluginService
from zentex.reflection.service import get_service as get_reflection_service
from zentex.tasks.service import get_service as get_task_service
from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.service import build_default_upgrade_runtime_components
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


class _AcceptanceTranscriptStore:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def write_entry(self, **payload: Any) -> None:
        self.entries.append(payload)

    def list_entries(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.entries)


class _AcceptanceMcpClient:
    def health_probe(self, config: McpServerConfig) -> bool:
        return True

    def list_tools(self, config: McpServerConfig) -> list[McpToolDescriptor]:
        return [
            McpToolDescriptor(
                tool_name="inspect",
                description=f"Inspect {config.server_id}",
                input_schema={"type": "object"},
                mutates_state=False,
                read_only_hint=True,
            )
        ]

    def invoke_tool(
        self,
        config: McpServerConfig,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        trace_id: str,
    ) -> dict[str, Any]:
        return {
            "summary": f"{tool_name} ok",
            "server_id": config.server_id,
            "arguments": arguments,
            "trace_id": trace_id,
        }


class _AcceptanceAgentBridge:
    async def check_health(self, _asset: Any) -> bool:
        return True

    async def perform_handshake(self, _asset: Any) -> dict[str, Any]:
        return {
            "capabilities": [{"name": "inspect"}],
            "latency_ms": 1.0,
        }


class _AcceptanceSession:
    def __init__(self, session_id: str = "acceptance-session") -> None:
        self.session_id = session_id
        self.last_turn_id = "acceptance-turn"
        self.workspace = "/acceptance"


class _AcceptanceSessionManager:
    def __init__(self) -> None:
        self._session = _AcceptanceSession()

    async def get_active_session(self, session_id: str) -> _AcceptanceSession:
        if session_id != self._session.session_id:
            raise ValueError(session_id)
        return self._session

    async def list_active_sessions(self) -> list[_AcceptanceSession]:
        return [self._session]

    async def create_session(self, workspace: str, session_id: str | None = None) -> _AcceptanceSession:
        self._session = _AcceptanceSession(session_id or "acceptance-session")
        self._session.workspace = workspace
        return self._session


class _AcceptanceNineQuestionStateManager:
    def __init__(self) -> None:
        self.state = self._blank_state()

    @staticmethod
    def _blank_state() -> dict[str, Any]:
        return {
            "question_snapshots": {
                f"q{i}": {
                    "tool_id": f"nine_questions.q{i}",
                    "summary": f"Q{i} acceptance baseline",
                    "confidence": 0.9,
                    "trace_id": f"q{i}:acceptance",
                    "result": {"status": "ready"},
                    "context_updates": {},
                }
                for i in range(1, 10)
            },
            "snapshot_version": 1,
            "revision": 1,
            "dirty_questions": [],
            "last_refresh_reason": "acceptance-bootstrap",
            "question_driver_refs": [f"q{i}" for i in range(1, 10)],
        }

    async def get_state(self, key: str) -> dict[str, Any]:
        if key != "nq-baseline":
            raise ValueError(key)
        return self.state

    async def bootstrap_state(self, key: str) -> dict[str, Any]:
        if key != "nq-baseline":
            raise ValueError(key)
        self.state = self._blank_state()
        return self.state

    async def update_state(self, key: str, **updates: Any) -> dict[str, Any]:
        if key != "nq-baseline":
            raise ValueError(key)
        self.state.update(updates)
        self.state["revision"] = int(self.state.get("revision", 0)) + 1
        return self.state


class _AcceptanceKernelFacade:
    def __init__(
        self,
        *,
        transcript_store: _AcceptanceTranscriptStore,
        session_manager: _AcceptanceSessionManager,
        state_manager: _AcceptanceNineQuestionStateManager,
    ) -> None:
        self._transcript_store = transcript_store
        self._session_manager = session_manager
        self._state_manager = state_manager

    def get_transcript_store(self) -> _AcceptanceTranscriptStore:
        return self._transcript_store

    def get_session_manager(self) -> _AcceptanceSessionManager:
        return self._session_manager

    def get_nine_question_state_manager(self) -> _AcceptanceNineQuestionStateManager:
        return self._state_manager

    def get_event_bus(self) -> None:
        return None

    def get_session_meta(self, session_id: str) -> dict[str, str] | None:
        return {"session_id": session_id} if session_id == "acceptance-session" else None

    def list_active_sessions(self) -> list[str]:
        return ["acceptance-session"]

    def create_kernel_session(self, user_id: str = "") -> str:
        return "acceptance-session"

    def get_nine_question_state(self) -> None:
        return None


def _build_mcp_service(transcript_store: _AcceptanceTranscriptStore) -> McpIntegrationService:
    cognitive_registry = CognitiveToolRegistry(transcript_store=transcript_store)
    execution_registry = ExecutionDomainRegistry()
    adapter = McpAdapterPlugin(
        plugin_id="mcp-acceptance-adapter",
        version="1.0.0",
        feature_code="acceptance.mcp",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["acceptance_regression"],
        revocation_reasons=["acceptance_disabled"],
        server_configs=[],
    )
    adapter.attach_runtime(
        client_factory=lambda _config: _AcceptanceMcpClient(),
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    return McpIntegrationService(adapter=adapter)


@pytest.fixture()
def acceptance_app() -> FastAPI:
    transcript_store = _AcceptanceTranscriptStore()
    session_manager = _AcceptanceSessionManager()
    state_manager = _AcceptanceNineQuestionStateManager()
    facade = _AcceptanceKernelFacade(
        transcript_store=transcript_store,
        session_manager=session_manager,
        state_manager=state_manager,
    )
    WebConsoleContainer.initialize(kernel_service=facade)

    app = FastAPI()
    app.include_router(api_router)

    app.state.transcript_store = transcript_store
    app.state.reflection_service = get_reflection_service()
    app.state.learning_service = get_learning_service()
    app.state.memory_service = get_memory_service()
    app.state.audit_service = get_audit_service()
    app.state.task_service = get_task_service()
    app.state.agent_coordination_service = get_agent_service()
    app.state.agent_coordination_service.bridge = _AcceptanceAgentBridge()
    app.state.cli_service = get_cli_service(transcript_store=transcript_store)
    app.state.mcp_service = _build_mcp_service(transcript_store)
    upgrade_components = build_default_upgrade_runtime_components(memory_service=app.state.memory_service)
    app.state.upgrade_management_store = upgrade_components.management_store
    app.state.plugin_evolution_runtime = upgrade_components.plugin_runtime
    app.state.upgrade_audit_store = upgrade_components.audit_store
    app.state.upgrade_memory_store = upgrade_components.memory_store
    app.state.upgrade_evidence_service = upgrade_components.evidence_service
    app.state.upgrade_execution_service = UpgradeExecutionService(
        management_store=upgrade_components.management_store,
        plugin_runtime=upgrade_components.plugin_runtime,
        evidence_service=upgrade_components.evidence_service,
    )

    plugin_service = SystemPluginService(db_path="app_data/plugins_acceptance.sqlite3")
    plugin_service.bootstrap()
    app.state.plugin_service = plugin_service
    app.state.plugin_feature_catalog = plugin_service.get_feature_catalog()
    app.state.managed_plugin_records = {}

    app.state.session = session_manager._session
    app.state.active_session = session_manager._session
    app.state.nine_question_service = NineQuestionService(
        facade=facade,
        state_manager=state_manager,
    )
    app.state.kuzu_adapter = None
    app.state.active_model_provider = SimpleNamespace(provider_name="acceptance-provider")
    return app


@pytest.fixture()
def client(acceptance_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(acceptance_app) as test_client:
        yield test_client
