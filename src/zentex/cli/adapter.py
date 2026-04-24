from __future__ import annotations
"""
📋 CLI Adapter Module - Command Line Interface Integration

职责：
- 负责 CLI (Command Line Interface) 适配器的初始化和配置
- 提供公开 API `create_cli_adapter_plugin()` 供 bootstrap 模块使用
- 管理外部 shell 工具与 Zentex 插件边界的集成
- 处理 subprocess 执行、进程管理和命令回显

关键导出：
- create_cli_adapter_plugin(audit_store, cognitive_registry) -> CliAdapterPlugin
  * 公开初始化函数，bootstrap 应通过此函数创建 CLI 适配器
  * 包含完整的 CLI 环境配置和工具注册，避免 bootstrap 直接导入内部类

设计原则（工程规范 4.3B）：
- Module Independence: 每个模块通过公开 API 初始化自己
- Clean Imports: 所有导入在模块顶部，无函数内导入
- Boundary Protection: 保护 CLI 工具与系统其他部分的边界

"""


import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Protocol, Set
from uuid import uuid4

from pydantic import ConfigDict, PrivateAttr, BaseModel
from enum import Enum

from zentex.cli.models import (
    CliInvocationResult,
    CliToolRegistrationConfig,
    CliToolRuntimeState,
)
from zentex.plugins.cognitive_spec import CognitiveToolSpec
from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
    BasePluginSpec,
)
from zentex.plugins.execution import (
    ActionExecutionReceipt,
    ActionIntent,
    ActionStatus,
    ExecutionDomainPlugin,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.kernel import AuditEventStore, AuditEventType

_MUTATING_TOKENS: Set[str] = {
    "rm", "del", "delete", "format", "mkfs", "dd", "chmod", "chown",
    "write", "overwrite", "truncate", "kill", "stop", "reboot", "shutdown",
    "sudo", "su", "apt", "brew", "npm", "pip", "git", "cp", "mv"
}

try:
    from plumbum import local as plumbum_local
except Exception:  # pragma: no cover - optional dependency
    plumbum_local = None

try:
    import pexpect
except Exception:  # pragma: no cover - optional dependency
    pexpect = None


def create_cli_adapter_plugin(
    transcript_store: "AuditEventStore",
    cognitive_registry: Any = None,
) -> "CliAdapterPlugin":
    """
    ✅ 公开 API - cli 模块负责自己的 adapter 初始化
    
    bootstrap 只调用此函数，不应 import CliAdapterPlugin 或相关内部类。
    所有 CLI 适配器配置在这里定义。
    
    Args:
        transcript_store: 用于审计的事件存储
        cognitive_registry: 可选的认知工具注册表
        
    Returns:
        CliAdapterPlugin 实例
    """
    # CLI 环境配置 - 所有 CLI 相关逻辑在这里
    adapter = CliAdapterPlugin(
        plugin_id="cli-adapter-dev",
        version="1.0.0",
        feature_code="external.cli",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["cli_adapter_regression"],
        revocation_reasons=["cli_adapter_disabled"],
    )
    
    adapter.attach_runtime(
        transport=SubprocessCliTransport(),
        transcript_store=transcript_store,
    )
    
    return adapter


class CliTransportClient(Protocol):
    def health_probe(self, config: CliToolRegistrationConfig) -> bool: ...

    def invoke_tool(
        self,
        config: CliToolRegistrationConfig,
        *,
        arguments: List[str],
        stdin_input: Optional[str],
        trace_id: str,
        working_directory: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> CliInvocationResult: ...


class SubprocessCliTransport:
    """Fail-closed shell executor using plumbum when available and subprocess otherwise."""

    def health_probe(self, config: CliToolRegistrationConfig) -> bool:
        executable = config.command_executable
        if "/" in executable:
            return Path(executable).exists()
        return shutil.which(executable) is not None

    def invoke_tool(
        self,
        config: CliToolRegistrationConfig,
        *,
        arguments: List[str],
        stdin_input: Optional[str],
        trace_id: str,
        working_directory: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> CliInvocationResult:
        command_line = [config.command_executable, *config.command_args, *arguments]
        env = {**config.env}
        cwd = working_directory or config.project_path

        try:
            if pexpect is not None and stdin_input and "\n" in stdin_input:
                child = pexpect.spawn(
                    command_line[0],
                    command_line[1:],
                    cwd=cwd,
                    env=env or None,
                    encoding="utf-8",
                    timeout=timeout_seconds,
                )
                child.send(stdin_input)
                child.sendeof()
                child.expect(pexpect.EOF)
                stdout = child.before or ""
                stderr = ""
                exit_code = int(child.exitstatus or 0)
            else:
                if plumbum_local is not None:
                    _ = plumbum_local[command_line[0]][command_line[1:]]
                completed = subprocess.run(  # noqa: S603
                    command_line,
                    input=stdin_input,
                    text=True,
                    capture_output=True,
                    cwd=cwd,
                    env=env or None,
                    timeout=timeout_seconds,
                    check=False,
                )
                stdout = completed.stdout
                stderr = completed.stderr
                exit_code = completed.returncode
        except (subprocess.TimeoutExpired, TimeoutError):
            return CliInvocationResult(
                tool_name=config.tool_name,
                status="timeout",
                trace_id=trace_id,
                exit_code=-1,
                stdout="",
                stderr=f"Transport error: Command timed out after {timeout_seconds}s",
                command_line=command_line,
                working_directory=cwd,
            )
        except (FileNotFoundError, PermissionError) as e:
            return CliInvocationResult(
                tool_name=config.tool_name,
                status="transport_error",
                trace_id=trace_id,
                exit_code=-1,
                stdout="",
                stderr=f"Transport error: {e}",
                command_line=command_line,
                working_directory=cwd,
            )
        except Exception as e:
            return CliInvocationResult(
                tool_name=config.tool_name,
                status="failed",
                trace_id=trace_id,
                exit_code=-1,
                stdout="",
                stderr=f"Unexpected transport error: {e}",
                command_line=command_line,
                working_directory=cwd,
            )

        return CliInvocationResult(
            tool_name=config.tool_name,
            status="success" if exit_code == 0 else "failed",
            trace_id=trace_id,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            command_line=command_line,
            working_directory=cwd,
        )


class CliCognitiveToolPlugin(CognitiveToolSpec):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    _transport: CliTransportClient = PrivateAttr()
    _config: CliToolRegistrationConfig = PrivateAttr()
    _transcript_store: AuditEventStore = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: CliTransportClient,
        config: CliToolRegistrationConfig,
        transcript_store: AuditEventStore,
    ) -> None:
        self._transport = transport
        self._config = config
        self._transcript_store = transcript_store

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        trace_id = str(context.get("trace_id") or f"cli-cognitive:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        stdin_input = json.dumps({"context": context}, ensure_ascii=False)
        result = self._transport.invoke_tool(
            self._config,
            arguments=[],
            stdin_input=stdin_input,
            trace_id=trace_id,
            working_directory=self._config.project_path,
        )
        self._transcript_store.write_entry(
            session_id=session_id,
            turn_id=turn_id,
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
            payload={"tool_name": self._config.tool_name, "mapped_domain": "cognitive", **result.model_dump(mode="json")},
            source="cli.adapter.cognitive",
            trace_id=trace_id,
        )
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=result.stdout.strip() or self.purpose,
            evidence=[{"tool_name": self._config.tool_name, "command_line": result.command_line}],
            context_updates={"cli_stdout": result.stdout},
            confidence=1.0 if result.exit_code == 0 else 0.0,
            risks=[result.stderr] if result.stderr else [],
        )


class CliExecutionDomainPlugin(ExecutionDomainPlugin):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    _transport: CliTransportClient = PrivateAttr()
    _config: CliToolRegistrationConfig = PrivateAttr()
    _transcript_store: AuditEventStore = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: CliTransportClient,
        config: CliToolRegistrationConfig,
        transcript_store: AuditEventStore,
    ) -> None:
        self._transport = transport
        self._config = config
        self._transcript_store = transcript_store

    def execute_action(self, intent: ActionIntent, context: Dict[str, Any]) -> ActionExecutionReceipt:
        trace_id = str(context.get("trace_id") or f"cli-execution:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        stdin_input = json.dumps(
            {"intent": intent.model_dump(mode="json"), "context": context},
            ensure_ascii=False,
        )
        result = self._transport.invoke_tool(
            self._config,
            arguments=[],
            stdin_input=stdin_input,
            trace_id=trace_id,
            working_directory=self._config.project_path,
        )
        self._transcript_store.write_entry(
            session_id=session_id,
            turn_id=turn_id,
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
            payload={"tool_name": self._config.tool_name, "mapped_domain": "execution", **result.model_dump(mode="json")},
            source="cli.adapter.execution",
            trace_id=trace_id,
        )
        return ActionExecutionReceipt(
            status=ActionStatus.SUCCESS if result.exit_code == 0 else ActionStatus.FAILED,
            evidence_payload=result.model_dump(mode="json"),
        )


class CliAdapterPlugin(FunctionalPluginSpec):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    purpose: str = "Adapt external CLI tools into cognitive or execution runtimes"

    _transport: CliTransportClient = PrivateAttr()
    _transcript_store: AuditEventStore = PrivateAttr()
    _registered_tools: Dict[str, CliToolRegistrationConfig] = PrivateAttr(default_factory=dict)
    _tool_states: Dict[str, CliToolRuntimeState] = PrivateAttr(default_factory=dict)
    _registered_plugin_ids: Set[str] = PrivateAttr(default_factory=set)

    @classmethod
    def plugin_kind(cls) -> str:
        return "cli_adapter"

    def attach_runtime(
        self,
        *,
        transport: CliTransportClient,
        transcript_store: AuditEventStore,
        cognitive_registry: Optional[Any] = None,
        execution_registry: Optional[Any] = None,
    ) -> None:
        self._transport = transport
        self._transcript_store = transcript_store

    def register_tool(self, config: CliToolRegistrationConfig) -> CliToolRuntimeState:
        normalized = CliToolRegistrationConfig.model_validate(config.model_dump(mode="json"))
        if normalized.tool_name in self._registered_tools:
            raise ValueError(f"CLI tool '{normalized.tool_name}' is already registered")
        executable = normalized.command_executable.strip()
        if not executable or any(token in executable for token in (" ", "\t", "|", ";", "&", ">", "<", "$", "`")):
            raise ValueError(
                "ValidationError: command_executable must be a bare executable path or command name, not a shell line."
            )
        lowered = executable.lower().rsplit("/", 1)[-1]
        if normalized.read_only_flag and lowered in _MUTATING_TOKENS:
            raise ValueError(
                "ValidationError: read-only CLI tools cannot register mutating executables."
            )
        if not self._transport.health_probe(normalized):
            raise FileNotFoundError(f"health probe failed for CLI tool: {normalized.command_executable}")
        state = self._build_tool_runtime_state(normalized)
        self._registered_tools[normalized.tool_name] = normalized
        self._tool_states[normalized.tool_name] = state
        return state

    def list_tool_states(self) -> List[CliToolRuntimeState]:
        return [self._tool_states[key] for key in sorted(self._tool_states.keys())]

    def activate_tool(self, tool_name: str) -> CliToolRuntimeState:
        config = self.get_tool_config(tool_name)
        if not self._transport.health_probe(config):
            raise FileNotFoundError(f"health probe failed for CLI tool: {config.command_executable}")
        state = self._build_tool_runtime_state(config).model_copy(update={"status": "active"})
        self._tool_states[tool_name] = state
        return state

    def disable_tool(self, tool_name: str) -> CliToolRuntimeState:
        state = self._tool_states.get(tool_name)
        if state is None:
            raise KeyError(tool_name)
        stopped = state.model_copy(update={"status": "stopped"})
        self._tool_states[tool_name] = stopped
        return stopped

    def delete_tool(self, tool_name: str) -> bool:
        if tool_name not in self._registered_tools:
            raise KeyError(tool_name)
        self._registered_tools.pop(tool_name, None)
        self._tool_states.pop(tool_name, None)
        return True

    def get_tool_health(self, tool_name: str) -> Dict[str, Any]:
        config = self.get_tool_config(tool_name)
        state = self._tool_states.get(tool_name)
        if state is None:
            raise KeyError(tool_name)
        healthy = state.status == "active" and self._transport.health_probe(config)
        return {
            "command_name": state.command_name,
            "status": state.status,
            "registered": True,
            "healthy": healthy,
            "last_test_status": None,
            "command_executable": config.command_executable,
        }

    def produce_sub_plugin_specs(self) -> List[tuple[BasePluginSpec, Any]]:
        """
        Produces Zentex plugin specifications for all managed CLI tools.
        Used by SystemPluginService to mount tools into the global bus.
        """
        specs = []
        for config in self._registered_tools.values():
            cli_id = f"cli:{config.tool_name}"
            feature_code = f"cli.{config.tool_name}"
            mapped_domain = "cognitive" if config.read_only_flag else "execution"
            
            if mapped_domain == "cognitive":
                spec = CliCognitiveToolPlugin(
                    plugin_id=cli_id,
                    version="1.0.0",
                    feature_code=feature_code,
                    is_concurrency_safe=True,
                    lifecycle_status=PluginLifecycleStatus.ACTIVE,
                    health_status=PluginHealthStatus.HEALTHY,
                    rollback_conditions=["cli_tool_regression"],
                    revocation_reasons=["cli_adapter_disabled"],
                    tool_type="cli_cognitive_tool",
                    purpose=config.description,
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                    required_context=["trace_id"],
                    trigger_conditions=["inspection"],
                    behavior_key=feature_code,
                    supports_multiple_plugins=False,
                    is_default_version=True,
                    is_official_release=True,
                    do_not_use_when=["cli_tool_degraded"],
                    read_only=True,
                    side_effect_free=True,
                )
                spec.attach_runtime(transport=self._transport, config=config, transcript_store=self._transcript_store)
            else:
                spec = CliExecutionDomainPlugin(
                    plugin_id=cli_id,
                    version="1.0.0",
                    feature_code=feature_code,
                    is_concurrency_safe=False,
                    lifecycle_status=PluginLifecycleStatus.ACTIVE,
                    health_status=PluginHealthStatus.HEALTHY,
                    rollback_conditions=["cli_tool_regression"],
                    revocation_reasons=["cli_adapter_disabled"],
                    execution_domain=config.execution_domain,
                    requires_cloud_audit=True,
                )
                spec.attach_runtime(transport=self._transport, config=config, transcript_store=self._transcript_store)
            specs.append((spec, config))
        return specs

    def get_tool_config(self, tool_name: str) -> CliToolRegistrationConfig:
        config = self._registered_tools.get(tool_name)
        if config is None:
            raise KeyError(tool_name)
        return config

    def invoke_tool(
        self,
        tool_name: str,
        *,
        arguments: List[Optional[str]] = None,
        stdin_input: Optional[str] = None,
        trace_id: Optional[str] = None,
        working_directory: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> CliInvocationResult:
        config = self.get_tool_config(tool_name)
        return self._transport.invoke_tool(
            config,
            arguments=list(arguments or []),
            stdin_input=stdin_input,
            trace_id=trace_id or f"cli-test:{uuid4().hex}",
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )

    def health_probe(self) -> PluginHealthStatus:
        if not self._registered_tools:
            return PluginHealthStatus.HEALTHY
        healthy = all(self._transport.health_probe(config) for config in self._registered_tools.values())
        return PluginHealthStatus.HEALTHY if healthy else PluginHealthStatus.DEGRADED

    def _build_tool_runtime_state(self, config: CliToolRegistrationConfig) -> CliToolRuntimeState:
        cli_id = f"cli:{config.tool_name}"
        feature_code = f"cli.{config.tool_name}"
        mapped_domain = "cognitive" if config.read_only_flag else "execution"
        return CliToolRuntimeState(
            command_name=config.tool_name,
            description=config.description,
            mapped_domain=mapped_domain,
            cli_id=cli_id,
            feature_code=feature_code,
            execution_domain=None if mapped_domain == "cognitive" else config.execution_domain,
            read_only=config.read_only_flag,
            side_effect_free=config.read_only_flag,
            mutates_state=not config.read_only_flag,
            requires_cloud_audit=not config.read_only_flag,
            help_doc_url=config.help_doc_url,
            project_path=config.project_path,
            project_name=config.project_name,
            project_description=config.project_description,
        )
