from __future__ import annotations
"""
📋 MCP Adapter Module - Model Context Protocol Integration

职责：
- 负责 MCP (Model Context Protocol) 适配器的初始化和配置
- 提供公开 API `create_mcp_adapter_plugin()` 供 bootstrap 模块使用
- 封装所有 MCP 相关配置（服务器配置、传输客户端、工具绑定）
- 不负责 web_console 相关的业务逻辑

关键导出：
- create_mcp_adapter_plugin(audit_store, cognitive_registry, defer_sync) -> (McpAdapterPlugin, ExecutionDomainRegistry)
  * 公开初始化函数，bootstrap 应通过此函数创建 MCP 适配器
  * 包含完整的 MCP 环境配置，避免 bootstrap 直接导入内部类

设计原则（工程规范 4.3B）：
- Module Independence: 每个模块通过公开 API 初始化自己
- No Web Console Coupling: 不依赖 web_console.build_managed_plugin_record
- Clean Imports: 所有导入在模块顶部，无函数内导入
"""


from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Set
from uuid import uuid4

from pydantic import ConfigDict, Field, PrivateAttr

from zentex.plugins.service import ExecutionDomainRegistry
from zentex.plugins.execution import (
    ActionExecutionReceipt,
    ActionIntent,
    ActionStatus,
    ExecutionDomainPlugin,
)
from zentex.mcp.models import (
    McpServerConfig,
    McpServerRuntimeState,
    McpToolBindingConfig,
    McpToolDescriptor,
    McpToolRuntimeState,
)
from zentex.plugins.cognitive_spec import CognitiveToolSpec
from zentex.plugins.contracts import FunctionalPluginSpec, PluginHealthStatus, PluginLifecycleStatus
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.plugins.service import CognitiveToolRegistry
from zentex.kernel import AuditEventStore, AuditEventType
from zentex.supervision.service import get_ai_supervisor


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
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    _transport: McpTransportClient = PrivateAttr()
    _server_config: McpServerConfig = PrivateAttr()
    _transcript_store: AuditEventStore = PrivateAttr()
    _server_id: str = PrivateAttr()
    _tool_name: str = PrivateAttr()
    _tool_description: str = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: McpTransportClient,
        server_config: McpServerConfig,
        transcript_store: AuditEventStore,
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
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
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
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    requires_cloud_audit: bool = False
    _transport: McpTransportClient = PrivateAttr()
    _server_config: McpServerConfig = PrivateAttr()
    _transcript_store: AuditEventStore = PrivateAttr()
    _server_id: str = PrivateAttr()
    _tool_name: str = PrivateAttr()
    _tool_description: str = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: McpTransportClient,
        server_config: McpServerConfig,
        transcript_store: AuditEventStore,
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
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
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
    _transcript_store: AuditEventStore = PrivateAttr()
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
        transcript_store: AuditEventStore,
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
        if any(item.server_id == config.server_id for item in self.server_configs):
            raise ValueError(f"MCP server '{config.server_id}' is already registered")
        self.server_configs.append(config)
        return self._sync_single_server(config)

    def activate_server(self, server_id: str) -> McpServerRuntimeState:
        config = next((item for item in self.server_configs if item.server_id == server_id), None)
        if config is None:
            raise KeyError(server_id)
        return self._sync_single_server(config)

    def disable_server(self, server_id: str) -> McpServerRuntimeState:
        state = self._server_states.get(server_id)
        if state is None:
            raise KeyError(server_id)
        stopped = state.model_copy(update={"status": "offline"})
        self._server_states[server_id] = stopped
        return stopped

    def delete_server(self, server_id: str) -> bool:
        if server_id not in self._server_states and not any(
            item.server_id == server_id for item in self.server_configs
        ):
            raise KeyError(server_id)
        self.server_configs[:] = [item for item in self.server_configs if item.server_id != server_id]
        self._server_states.pop(server_id, None)
        self._registered_tool_ids = {
            tool_id for tool_id in self._registered_tool_ids if not tool_id.startswith(f"mcp:{server_id}:")
        }
        return True

    def get_server_health(self, server_id: str) -> Dict[str, Any]:
        state = self._server_states.get(server_id)
        if state is None:
            raise KeyError(server_id)
        return {
            "server_id": state.server_id,
            "status": state.status,
            "tool_count": state.tool_count,
            "error_message": state.error_message,
            "healthy": state.status == "online" and state.error_message is None,
        }

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
            reg = self._register_tool(config, tool, binding, client)
            if reg is not None:
                runtime_tools.append(reg)

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
        mcp_id = f"mcp:{config.server_id}:{tool.tool_name}"
        feature_code = f"mcp.{config.server_id}.{tool.tool_name}"
        if mcp_id in self._registered_tool_ids:
            return McpToolRuntimeState(
                tool_name=tool.tool_name,
                description=tool.description,
                mapped_domain=binding.domain,
                mcp_id=mcp_id,
                feature_code=feature_code,
                execution_domain=binding.execution_domain if binding.domain == "execution" else None,
                read_only=binding.read_only,
                side_effect_free=binding.side_effect_free,
                mutates_state=binding.mutates_state,
                requires_cloud_audit=binding.requires_cloud_audit,
            )

        if binding.domain == "cognitive":
            if self._cognitive_registry is None:
                import logging
                logging.getLogger(__name__).debug("Deferred MCP cognitive tool registration: registry not yet attached.")
                return None

            plugin = McpCognitiveToolPlugin(
                plugin_id=mcp_id,
                version="1.0.0",
                feature_code=feature_code,
                is_concurrency_safe=True,
                lifecycle_status=PluginLifecycleStatus.ACTIVE,
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
                raise RuntimeError(f"Failed to register MCP cognitive tool: {mcp_id}")
            self._cognitive_registry.promote_plugin(mcp_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "mcp sync")
            self._cognitive_registry.promote_plugin(mcp_id, PluginLifecycleStatus.ACTIVE, "mcp sync")
            self._registered_tool_ids.add(mcp_id)
        else:
            if self._execution_registry is None:
                import logging
                logging.getLogger(__name__).debug("Deferred MCP execution tool registration: registry not yet attached.")
                return None

            plugin = McpExecutionDomainPlugin(
                plugin_id=mcp_id,
                version="1.0.0",
                feature_code=feature_code,
                is_concurrency_safe=False,
                lifecycle_status=PluginLifecycleStatus.ACTIVE,
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
                raise RuntimeError(f"Failed to register MCP execution tool: {mcp_id}")
            self._execution_registry.promote_plugin(mcp_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "mcp sync")
            self._execution_registry.promote_plugin(mcp_id, PluginLifecycleStatus.ACTIVE, "mcp sync")
            self._registered_tool_ids.add(mcp_id)

        return McpToolRuntimeState(
            tool_name=tool.tool_name,
            description=tool.description,
            mapped_domain=binding.domain,
            mcp_id=mcp_id,
            feature_code=feature_code,
            execution_domain=binding.execution_domain if binding.domain == "execution" else None,
            read_only=binding.read_only,
            side_effect_free=binding.side_effect_free,
            mutates_state=binding.mutates_state,
            requires_cloud_audit=binding.requires_cloud_audit,
        )


def create_mcp_adapter_plugin(
    transcript_store: AuditEventStore,
    cognitive_registry: CognitiveToolRegistry,
    defer_sync: bool = False,
) -> tuple[McpAdapterPlugin, ExecutionDomainRegistry]:
    """
    ✅ 公开 API - mcp 模块负责自己的 adapter 初始化
    
    bootstrap 只调用此函数，不应 import McpAdapterPlugin 或相关内部类。
    所有 MCP 适配器配置在这里定义。
    
    Args:
        transcript_store: 审计事件存储
        cognitive_registry: 认知工具注册表
        defer_sync: 是否延后服务器同步到后台
        
    Returns:
        元组 (McpAdapterPlugin, ExecutionDomainRegistry)
    """
    from threading import Thread
    import logging
    from zentex.mcp.sdk_transport import build_official_mcp_client_factory
    
    logger = logging.getLogger(__name__)
    
    # MCP 环境配置 - 所有 MCP 相关逻辑在这里
    execution_registry = ExecutionDomainRegistry()
    server_configs = [
        McpServerConfig(
            server_id="knowledge-hub",
            transport_type="stdio",
            command="uvx",
            args=["knowledge-hub-mcp"],
            env={"KNOWLEDGE_ENV": "dev"},
            tool_bindings=[
                McpToolBindingConfig(
                    tool_name="search_documents",
                    domain="cognitive",
                    read_only=True,
                    side_effect_free=True,
                    mutates_state=False,
                )
            ],
        ),
        McpServerConfig(
            server_id="ops-bridge",
            transport_type="sse",
            command="https://ops.example.invalid/mcp",
            args=[],
            env={},
        ),
    ]

    # 创建适配器
    adapter = McpAdapterPlugin(
        plugin_id="mcp-adapter-core",
        version="1.0.0",
        feature_code="external.mcp",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["mcp_adapter_regression"],
        revocation_reasons=["mcp_adapter_disabled"],
        health_probe_endpoint="mcp://health",
        server_configs=server_configs,
    )
    
    # 运行时附件
    adapter.attach_runtime(
        client_factory=build_official_mcp_client_factory(),
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    
    # 同步服务器
    if defer_sync:
        def _sync_bg():
            try:
                adapter.sync_servers()
            except Exception as e:
                logger.error(f"FATAL: Deferred MCP sync failed globally: {e}")
                # Fail-Closed: Manually mark all configuring servers as degraded so health checks visibly fail
                for config in adapter.server_configs:
                    if config.server_id not in adapter._server_states:
                        adapter._server_states[config.server_id] = McpServerRuntimeState(
                            server_id=config.server_id,
                            transport_type=config.transport_type,
                            status="degraded",
                            tool_count=0,
                            error_message=f"Background sync catastrophic failure: {e}",
                            tools=[],
                        )
        Thread(target=_sync_bg, name="mcp-bg-sync", daemon=True).start()
    else:
        adapter.sync_servers()
    
    return adapter, execution_registry
