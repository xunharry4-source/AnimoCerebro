from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Set
from uuid import uuid4

from pydantic import ConfigDict, Field, PrivateAttr

from zentex.core.execution_registry import ExecutionDomainRegistry
from zentex.core.execution_spec import (
    ActionExecutionReceipt,
    ActionIntent,
    ActionStatus,
    ExecutionDomainPlugin,
)
from zentex.core.mcp import (
    McpServerConfig,
    McpServerRuntimeState,
    McpToolBindingConfig,
    McpToolDescriptor,
    McpToolRuntimeState,
)
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore


class McpTransportClient(Protocol):
    def list_tools(self, config: McpServerConfig) -> List[McpToolDescriptor]: ...

    def invoke_tool(
        self,
        config: McpServerConfig,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]: ...

    def health_probe(self, config: McpServerConfig) -> bool: ...


class McpCognitiveToolPlugin(CognitiveToolSpec):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    _transport: McpTransportClient = PrivateAttr()
    _server_config: McpServerConfig = PrivateAttr()
    _transcript_store: BrainTranscriptStore = PrivateAttr()
    _server_id: str = PrivateAttr()
    _tool_name: str = PrivateAttr()
    _tool_description: str = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: McpTransportClient,
        server_config: McpServerConfig,
        transcript_store: BrainTranscriptStore,
        tool_name: str,
        tool_description: str,
    ) -> None:
        self._transport = transport
        self._server_config = server_config
        self._transcript_store = transcript_store
        self._server_id = server_config.server_id
        self._tool_name = tool_name
        self._tool_description = tool_description

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        trace_id = str(context.get("trace_id") or f"mcp-cognitive:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        arguments = {
            "context": {
                key: value
                for key, value in context.items()
                if key not in {"transcript_store", "model_provider", "plugin_registry"}
            }
        }
        self._record_event(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            phase="invoked",
            payload={"arguments": arguments},
        )
        # Start supervision record
        from zentex.supervision.ai_supervisor import get_ai_supervisor
        supervisor = get_ai_supervisor()
        supervision_record = supervisor.start_monitoring(
            task_id=turn_id,
            action_type=f"mcp_cognitive:{self._tool_name}",
            parameters={"server_id": self._server_id, "tool_name": self._tool_name, **arguments}
        )

        try:
            raw = self._transport.invoke_tool(
                self._server_config,
                tool_name=self._tool_name,
                arguments=arguments,
                trace_id=trace_id,
            )
            supervisor.update_execution(supervision_record.record_id, "completed", result=raw)
        except Exception as exc:
            supervisor.update_execution(supervision_record.record_id, "failed", error=str(exc))
            self._record_event(
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                phase="failed",
                payload={"error_type": exc.__class__.__name__, "error_message": str(exc)},
            )
            raise

        self._record_event(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            phase="completed",
            payload={"result": raw},
        )
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=str(raw.get("summary") or self._tool_description),
            evidence=[{"server_id": self._server_id, "tool_name": self._tool_name}],
            context_updates=dict(raw.get("context_updates") or {}),
            confidence=float(raw.get("confidence") or 1.0),
            proposals=list(raw.get("proposals") or []),
            ranked_options=list(raw.get("ranked_options") or []),
            risks=list(raw.get("risks") or []),
            uncertainties=list(raw.get("uncertainties") or []),
        )

    def _record_event(
        self,
        *,
        session_id: str,
        turn_id: str,
        trace_id: str,
        phase: str,
        payload: Dict[str, Any],
    ) -> None:
        self._transcript_store.write_entry(
            session_id=session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
            payload={
                "server_id": self._server_id,
                "tool_name": self._tool_name,
                "mapped_domain": "cognitive",
                "phase": phase,
                **payload,
            },
            source="mcp.adapter.cognitive",
            trace_id=trace_id,
        )


class McpExecutionDomainPlugin(ExecutionDomainPlugin):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    _transport: McpTransportClient = PrivateAttr()
    _server_config: McpServerConfig = PrivateAttr()
    _transcript_store: BrainTranscriptStore = PrivateAttr()
    _server_id: str = PrivateAttr()
    _tool_name: str = PrivateAttr()
    _tool_description: str = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: McpTransportClient,
        server_config: McpServerConfig,
        transcript_store: BrainTranscriptStore,
        tool_name: str,
        tool_description: str,
    ) -> None:
        self._transport = transport
        self._server_config = server_config
        self._transcript_store = transcript_store
        self._server_id = server_config.server_id
        self._tool_name = tool_name
        self._tool_description = tool_description

    def execute_action(self, intent: ActionIntent, context: Dict[str, Any]) -> ActionExecutionReceipt:
        trace_id = str(context.get("trace_id") or f"mcp-execution:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        arguments = {
            "intent": intent.model_dump(mode="json"),
            "context": {key: value for key, value in context.items() if key != "transcript_store"},
        }
        self._record_event(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            phase="invoked",
            payload={"arguments": arguments},
        )
        # Start supervision record
        from zentex.supervision.ai_supervisor import get_ai_supervisor
        supervisor = get_ai_supervisor()
        supervision_record = supervisor.start_monitoring(
            task_id=turn_id,
            action_type=f"mcp_execution:{self._tool_name}",
            parameters={"server_id": self._server_id, "tool_name": self._tool_name, **arguments}
        )

        try:
            raw = self._transport.invoke_tool(
                self._server_config,
                tool_name=self._tool_name,
                arguments=arguments,
                trace_id=trace_id,
            )
            supervisor.update_execution(supervision_record.record_id, "completed", result=raw)
        except Exception as exc:
            supervisor.update_execution(supervision_record.record_id, "failed", error=str(exc))
            self._record_event(
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                phase="failed",
                payload={"error_type": exc.__class__.__name__, "error_message": str(exc)},
            )
            raise

        self._record_event(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            phase="completed",
            payload={"result": raw},
        )
        return ActionExecutionReceipt(
            status=ActionStatus.SUCCESS,
            evidence_payload={
                "server_id": self._server_id,
                "tool_name": self._tool_name,
                "trace_id": trace_id,
                "result": raw,
                "execution_domain": self.execution_domain,
            },
        )

    def _record_event(
        self,
        *,
        session_id: str,
        turn_id: str,
        trace_id: str,
        phase: str,
        payload: Dict[str, Any],
    ) -> None:
        self._transcript_store.write_entry(
            session_id=session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
            payload={
                "server_id": self._server_id,
                "tool_name": self._tool_name,
                "mapped_domain": "execution",
                "phase": phase,
                **payload,
            },
            source="mcp.adapter.execution",
            trace_id=trace_id,
        )


class McpAdapterPlugin(FunctionalPluginSpec):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    server_configs: List[McpServerConfig] = Field(default_factory=list)
    purpose: str = "Adapt external MCP servers into cognitive or execution runtimes"

    _client_factory: Callable[[McpServerConfig], McpTransportClient] = PrivateAttr()
    _transcript_store: BrainTranscriptStore = PrivateAttr()
    _cognitive_registry: CognitiveToolRegistry = PrivateAttr()
    _execution_registry: ExecutionDomainRegistry = PrivateAttr()
    _server_states: Dict[str, McpServerRuntimeState] = PrivateAttr(default_factory=dict)
    _registered_tool_ids: Set[str] = PrivateAttr(default_factory=set)

    @classmethod
    def plugin_kind(cls) -> str:
        return "mcp_adapter"

    def attach_runtime(
        self,
        *,
        client_factory: Callable[[McpServerConfig], McpTransportClient],
        transcript_store: BrainTranscriptStore,
        cognitive_registry: CognitiveToolRegistry,
        execution_registry: ExecutionDomainRegistry,
    ) -> None:
        self._client_factory = client_factory
        self._transcript_store = transcript_store
        self._cognitive_registry = cognitive_registry
        self._execution_registry = execution_registry

    def sync_servers(self) -> List[McpServerRuntimeState]:
        states: List[McpServerRuntimeState] = []
        for config in self.server_configs:
            states.append(self._sync_single_server(config))
        return states

    def list_server_states(self) -> List[McpServerRuntimeState]:
        return [self._server_states[key] for key in sorted(self._server_states.keys())]

    def register_server(self, config: McpServerConfig) -> McpServerRuntimeState:
        self.server_configs.append(config)
        return self._sync_single_server(config)

    def invoke_tool(
        self,
        server_id: str,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        config = next((item for item in self.server_configs if item.server_id == server_id), None)
        if config is None:
            raise KeyError(server_id)
        client = self._client_factory(config)
        return client.invoke_tool(
            config,
            tool_name=tool_name,
            arguments=arguments,
            trace_id=trace_id,
        )

    def health_probe(self) -> PluginHealthStatus:
        statuses = {state.status for state in self._server_states.values()}
        if not statuses:
            return PluginHealthStatus.UNKNOWN
        if statuses == {"online"}:
            return PluginHealthStatus.HEALTHY
        if "degraded" in statuses:
            return PluginHealthStatus.DEGRADED
        return PluginHealthStatus.UNHEALTHY

    def _sync_single_server(self, config: McpServerConfig) -> McpServerRuntimeState:
        client = self._client_factory(config)
        try:
            if not client.health_probe(config):
                raise TimeoutError(f"MCP server health probe failed: {config.server_id}")
            tools = client.list_tools(config)
        except Exception as exc:
            state = McpServerRuntimeState(
                server_id=config.server_id,
                transport_type=config.transport_type,
                status="degraded",
                tool_count=0,
                error_message=str(exc),
                tools=[],
            )
            self._server_states[config.server_id] = state
            return state

        runtime_tools: List[McpToolRuntimeState] = []
        for tool in tools:
            binding = self._resolve_binding(config, tool)
            runtime_tools.append(self._register_tool(config, tool, binding, client))

        state = McpServerRuntimeState(
            server_id=config.server_id,
            transport_type=config.transport_type,
            status="online",
            tool_count=len(runtime_tools),
            error_message=None,
            tools=runtime_tools,
        )
        self._server_states[config.server_id] = state
        return state

    def _resolve_binding(self, config: McpServerConfig, tool: McpToolDescriptor) -> McpToolBindingConfig:
        explicit = next((item for item in config.tool_bindings if item.tool_name == tool.tool_name), None)
        if explicit is not None:
            return McpToolBindingConfig.model_validate(
                {
                    **explicit.model_dump(mode="json"),
                    "mutates_state": tool.mutates_state or explicit.mutates_state,
                }
            )

        lowered = f"{tool.tool_name} {tool.description}".lower()
        mutating = tool.mutates_state or any(
            token in lowered
            for token in ("write", "delete", "update", "create", "post", "patch", "remove", "modify")
        )
        if mutating:
            return McpToolBindingConfig(
                tool_name=tool.tool_name,
                domain="execution",
                read_only=False,
                side_effect_free=False,
                mutates_state=True,
                requires_cloud_audit=True,
                execution_domain="mcp",
            )
        return McpToolBindingConfig(
            tool_name=tool.tool_name,
            domain="cognitive",
            read_only=True,
            side_effect_free=True,
            mutates_state=False,
        )

    def _register_tool(
        self,
        config: McpServerConfig,
        tool: McpToolDescriptor,
        binding: McpToolBindingConfig,
        client: McpTransportClient,
    ) -> McpToolRuntimeState:
        plugin_id = f"mcp:{config.server_id}:{tool.tool_name}"
        feature_code = f"mcp.{config.server_id}.{tool.tool_name}"
        if plugin_id in self._registered_tool_ids:
            return McpToolRuntimeState(
                tool_name=tool.tool_name,
                description=tool.description,
                mapped_domain=binding.domain,
                plugin_id=plugin_id,
                feature_code=feature_code,
                execution_domain=binding.execution_domain if binding.domain == "execution" else None,
                read_only=binding.read_only,
                side_effect_free=binding.side_effect_free,
                mutates_state=binding.mutates_state,
                requires_cloud_audit=binding.requires_cloud_audit,
            )

        if binding.domain == "cognitive":
            plugin = McpCognitiveToolPlugin(
                plugin_id=plugin_id,
                version="1.0.0",
                feature_code=feature_code,
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["mcp_tool_regression"],
                revocation_reasons=["mcp_server_isolated"],
                tool_type="mcp_cognitive_tool",
                purpose=tool.description,
                input_schema=tool.input_schema,
                output_schema={"type": "object"},
                required_context=["trace_id"],
                trigger_conditions=["inspection"],
                behavior_key=feature_code,
                supports_multiple_plugins=False,
                is_default_version=True,
                is_official_release=True,
                do_not_use_when=["mcp_server_degraded"],
                read_only=True,
                side_effect_free=True,
            )
            plugin.attach_runtime(
                transport=client,
                server_config=config,
                transcript_store=self._transcript_store,
                tool_name=tool.tool_name,
                tool_description=tool.description,
            )
            registration = self._cognitive_registry.register(plugin, description=tool.description)
            if registration is None:
                raise RuntimeError(f"Failed to register MCP cognitive tool: {plugin_id}")
            self._cognitive_registry.promote_plugin(plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "mcp sync")
            self._cognitive_registry.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, "mcp sync")
            self._registered_tool_ids.add(plugin_id)
        else:
            plugin = McpExecutionDomainPlugin(
                plugin_id=plugin_id,
                version="1.0.0",
                feature_code=feature_code,
                is_concurrency_safe=False,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["mcp_tool_regression"],
                revocation_reasons=["mcp_server_isolated"],
                execution_domain=binding.execution_domain,
                requires_cloud_audit=binding.requires_cloud_audit,
            )
            plugin.attach_runtime(
                transport=client,
                server_config=config,
                transcript_store=self._transcript_store,
                tool_name=tool.tool_name,
                tool_description=tool.description,
            )
            registered = self._execution_registry.register(plugin)
            if registered is None:
                raise RuntimeError(f"Failed to register MCP execution tool: {plugin_id}")
            self._execution_registry.promote_plugin(plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "mcp sync")
            self._execution_registry.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, "mcp sync")
            self._registered_tool_ids.add(plugin_id)

        return McpToolRuntimeState(
            tool_name=tool.tool_name,
            description=tool.description,
            mapped_domain=binding.domain,
            plugin_id=plugin_id,
            feature_code=feature_code,
            execution_domain=binding.execution_domain if binding.domain == "execution" else None,
            read_only=binding.read_only,
            side_effect_free=binding.side_effect_free,
            mutates_state=binding.mutates_state,
            requires_cloud_audit=binding.requires_cloud_audit,
        )


class FakeMcpTransportClient:
    def __init__(
        self,
        *,
        tools: List[McpToolDescriptor],
        invocations: Dict[str, Dict[str, Any]] | None = None,
        healthy: bool = True,
        fail_with: Optional[Exception] = None,
    ) -> None:
        self._tools = tools
        self._invocations = invocations or {}
        self._healthy = healthy
        self._fail_with = fail_with

    def list_tools(self, config: McpServerConfig) -> List[McpToolDescriptor]:
        if self._fail_with is not None:
            raise self._fail_with
        return list(self._tools)

    def invoke_tool(
        self,
        config: McpServerConfig,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        if self._fail_with is not None:
            raise self._fail_with
        payload = dict(self._invocations.get(tool_name) or {})
        payload.setdefault("summary", f"{tool_name} completed")
        payload.setdefault("trace_id", trace_id)
        payload.setdefault("arguments_echo", arguments)
        return payload

    def health_probe(self, config: McpServerConfig) -> bool:
        if self._fail_with is not None:
            raise self._fail_with
        return self._healthy
