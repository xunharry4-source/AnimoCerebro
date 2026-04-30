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
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, List, Optional, Protocol, Set
from uuid import uuid4

from pydantic import ConfigDict, PrivateAttr, BaseModel
from enum import Enum

from zentex.cli.models import (
    CliInvocationResult,
    CliToolRegistrationConfig,
    CliToolRuntimeState,
)
from zentex.agents.auth import AgentAuthError, AgentAuthService, AgentResolvedAuth
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

_MUTATING_ARG_FRAGMENTS: Set[str] = {
    "write_text", "write_bytes", ".write(", "open(", "truncate(", "unlink(",
    "remove(", "rmtree", "mkdir(", "rename(", "replace(", "chmod(", "chown(",
    "git commit", "git push", "git reset", "git checkout", "rm ", "rm -",
    "touch ", "mkdir ", "mv ", "cp ", "tee ", ">",
}

_DANGEROUS_ARG_FRAGMENTS: Set[str] = {
    ";",
    "|",
    "&&",
    "||",
    "`",
    "$(",
    ">",
    "<",
    "../",
    "..\\",
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


def _redact_known_values(text: str, auth_data: Dict[str, Any]) -> str:
    redacted = text
    for value in auth_data.values():
        if isinstance(value, str) and value and len(value) >= 4:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


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
            executable_exists = Path(executable).exists()
        else:
            executable_exists = shutil.which(executable) is not None
        if not executable_exists:
            return False

        probe_commands = self._build_health_probe_commands(config)
        for command in probe_commands:
            try:
                completed = subprocess.run(  # noqa: S603
                    command,
                    text=True,
                    capture_output=True,
                    env={**os.environ, **dict(config.env)} if config.env else None,
                    timeout=5,
                    check=False,
                )
            except (subprocess.TimeoutExpired, TimeoutError, FileNotFoundError, PermissionError):
                continue
            except Exception:
                continue
            if completed.returncode == 0:
                return True
        return False

    @staticmethod
    def _build_health_probe_commands(config: CliToolRegistrationConfig) -> List[List[str]]:
        executable = config.command_executable
        if config.health_probe_args:
            return [[executable, *config.command_args, *config.health_probe_args]]
        return [
            [executable, *config.command_args, "--version"],
            [executable, *config.command_args, "--help"],
        ]

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
        env = {**os.environ, **dict(config.env)} if config.env else None
        cwd = working_directory or config.project_path
        started_at = perf_counter()

        try:
            if pexpect is not None and stdin_input and "\n" in stdin_input:
                child = pexpect.spawn(
                    command_line[0],
                    command_line[1:],
                    cwd=cwd,
                    env=env,
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
                    env=env,
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
                duration_ms=_elapsed_ms(started_at),
                failure_category="timeout",
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
                duration_ms=_elapsed_ms(started_at),
                failure_category="transport_error",
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
                duration_ms=_elapsed_ms(started_at),
                failure_category="unexpected_transport_error",
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
            duration_ms=_elapsed_ms(started_at),
            failure_category=None if exit_code == 0 else "non_zero_exit",
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
    _auth_service: Optional[AgentAuthService] = PrivateAttr(default=None)

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
        auth_service: Optional[AgentAuthService] = None,
    ) -> None:
        self._transport = transport
        self._transcript_store = transcript_store
        self._auth_service = auth_service

    def attach_auth_service(self, auth_service: AgentAuthService) -> None:
        self._auth_service = auth_service

    def register_tool(self, config: CliToolRegistrationConfig) -> CliToolRuntimeState:
        normalized = CliToolRegistrationConfig.model_validate(config.model_dump(mode="json"))
        if normalized.tool_name in self._registered_tools:
            self._write_registration_rejection_audit(
                config=normalized,
                reason=f"CLI tool '{normalized.tool_name}' is already registered",
                failure_category="duplicate_registration",
            )
            raise ValueError(f"CLI tool '{normalized.tool_name}' is already registered")
        executable = normalized.command_executable.strip()
        if not executable or any(token in executable for token in (" ", "\t", "|", ";", "&", ">", "<", "$", "`")):
            self._write_registration_rejection_audit(
                config=normalized,
                reason="command_executable must be a bare executable path or command name, not a shell line",
                failure_category="invalid_executable_schema",
            )
            raise ValueError(
                "ValidationError: command_executable must be a bare executable path or command name, not a shell line."
            )
        if normalized.read_only_flag and self._looks_like_mutating_command(normalized):
            self._write_registration_rejection_audit(
                config=normalized,
                reason="read-only CLI tools cannot register mutating executables",
                failure_category="read_only_masquerade",
            )
            raise ValueError(
                "ValidationError: read-only CLI tools cannot register mutating executables."
            )
        if self._contains_direct_secret(normalized.env) or self._contains_direct_secret(normalized.auth_config):
            self._write_registration_rejection_audit(
                config=normalized,
                reason="CLI auth secrets must be stored in the encrypted credential vault, not env/auth_config",
                failure_category="direct_secret_rejected",
            )
            raise ValueError("ValidationError: CLI auth secrets must use encrypted credential vault references.")
        probe_config = normalized
        if normalized.auth_required_for_health:
            probe_auth = self._resolve_cli_auth(normalized)
            probe_config = self._effective_config(normalized, probe_auth)
        if not self._transport.health_probe(probe_config):
            self._write_registration_rejection_audit(
                config=normalized,
                reason=f"health probe failed for CLI tool: {normalized.command_executable}",
                failure_category="command_missing",
            )
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
        state = self._tool_states.get(tool_name)
        trace = trace_id or f"cli-test:{uuid4().hex}"
        if state is None or state.status in {"revoked", "stopped"}:
            result = CliInvocationResult(
                tool_name=config.tool_name,
                status="failed",
                trace_id=trace,
                exit_code=-1,
                stdout="",
                stderr=f"CLI tool '{tool_name}' is not active",
                command_line=[config.command_executable, *config.command_args, *list(arguments or [])],
                working_directory=working_directory or config.project_path,
                failure_category="inactive_tool",
            )
            self._write_invocation_audit(config=config, result=result, mapped_domain="inactive")
            return result

        argument_violations = self._find_dangerous_argument_patterns(list(arguments or []))
        if argument_violations:
            result = CliInvocationResult(
                tool_name=config.tool_name,
                status="failed",
                trace_id=trace,
                exit_code=-2,
                stdout="",
                stderr=f"ValidationError: dangerous CLI argument pattern blocked: {argument_violations}",
                command_line=[config.command_executable, *config.command_args, *list(arguments or [])],
                working_directory=working_directory or config.project_path,
                failure_category="dangerous_argument",
                preflight_blocked=True,
            )
            self._write_invocation_audit(
                config=config,
                result=result,
                mapped_domain="cognitive" if config.read_only_flag else "execution",
            )
            return result

        resolved_auth = self._resolve_cli_auth(config)
        result = self._transport.invoke_tool(
            self._effective_config(config, resolved_auth),
            arguments=[*list(arguments or []), *resolved_auth.arguments],
            stdin_input=resolved_auth.stdin_input if resolved_auth.stdin_input is not None else stdin_input,
            trace_id=trace,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        result = self._redact_cli_result(result, resolved_auth)
        self._write_invocation_audit(
            config=config,
            result=result,
            mapped_domain="cognitive" if config.read_only_flag else "execution",
        )
        return result

    def _resolve_cli_auth(self, config: CliToolRegistrationConfig) -> AgentResolvedAuth:
        if not config.auth_config:
            return AgentResolvedAuth()
        if self._auth_service is None:
            raise AgentAuthError("CLI auth_config requires AgentAuthService")
        return self._auth_service.resolve_cli(config)

    @staticmethod
    def _effective_config(config: CliToolRegistrationConfig, auth: AgentResolvedAuth) -> CliToolRegistrationConfig:
        if not auth.env:
            return config
        return config.model_copy(update={"env": {**dict(config.env), **auth.env}})

    @staticmethod
    def _redact_cli_result(result: CliInvocationResult, auth: AgentResolvedAuth) -> CliInvocationResult:
        redacted_stdout = _redact_known_values(result.stdout, auth.auth_data)
        redacted_stderr = _redact_known_values(result.stderr, auth.auth_data)
        if redacted_stdout == result.stdout and redacted_stderr == result.stderr:
            return result
        return result.model_copy(update={"stdout": redacted_stdout, "stderr": redacted_stderr})

    @staticmethod
    def _contains_direct_secret(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        for key, item in value.items():
            lowered = str(key).lower().replace("-", "_")
            if any(token in lowered for token in ("api_key", "token", "password", "secret", "authorization")):
                if isinstance(item, str) and "$auth." not in item and "$credential." not in item:
                    return True
            if isinstance(item, dict) and CliAdapterPlugin._contains_direct_secret(item):
                return True
        return False

    def diagnose_cli_execution_closure(self) -> Dict[str, Any]:
        from zentex.cli.lifecycle_diagnostics import build_cli_execution_diagnostic_report

        report = build_cli_execution_diagnostic_report(
            configs=list(self._registered_tools.values()),
            states=self.list_tool_states(),
            audit_entries=self._read_cli_audit_entries(limit=1000),
        )
        self._write_closure_audit("cli_execution_closure_diagnosed", report.to_dict())
        return report.to_dict()

    def run_cli_fault_injection_matrix(self) -> Dict[str, Any]:
        from zentex.cli.lifecycle_diagnostics import (
            build_cli_execution_diagnostic_report,
            build_cli_fault_injection_report,
        )

        diagnostic = build_cli_execution_diagnostic_report(
            configs=list(self._registered_tools.values()),
            states=self.list_tool_states(),
            audit_entries=self._read_cli_audit_entries(limit=1000),
        )
        report = build_cli_fault_injection_report(diagnostic)
        self._write_closure_audit("cli_fault_matrix_executed", report.to_dict())
        return report.to_dict()

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

    @staticmethod
    def _looks_like_mutating_command(config: CliToolRegistrationConfig) -> bool:
        executable = config.command_executable.strip().lower().rsplit("/", 1)[-1]
        if executable in _MUTATING_TOKENS:
            return True
        rendered_args = " ".join(str(arg or "") for arg in config.command_args).lower()
        return any(fragment in rendered_args for fragment in _MUTATING_ARG_FRAGMENTS)

    @staticmethod
    def _find_dangerous_argument_patterns(arguments: List[Optional[str]]) -> List[str]:
        rendered = " ".join(str(arg or "") for arg in arguments).lower()
        found = sorted(fragment for fragment in _DANGEROUS_ARG_FRAGMENTS if fragment in rendered)
        mutating = sorted(fragment for fragment in _MUTATING_ARG_FRAGMENTS if fragment in rendered)
        return [*found, *mutating]

    def _write_registration_rejection_audit(
        self,
        *,
        config: CliToolRegistrationConfig,
        reason: str,
        failure_category: str,
    ) -> None:
        if self._transcript_store is None:
            return
        trace_id = f"cli-register:{uuid4().hex}"
        self._transcript_store.write_entry(
            session_id="cli-management",
            turn_id=trace_id,
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
            timestamp=datetime.now(timezone.utc),
            payload={
                "tool_name": config.tool_name,
                "status": "rejected",
                "trace_id": trace_id,
                "command_executable": config.command_executable,
                "command_args": list(config.command_args),
                "read_only": config.read_only_flag,
                "reason": reason,
                "failure_category": failure_category,
            },
            source="cli.adapter.registration",
            trace_id=trace_id,
        )

    def _write_closure_audit(self, event_name: str, payload: Dict[str, Any]) -> None:
        if self._transcript_store is None:
            return
        trace_id = f"cli-closure:{uuid4().hex}"
        self._transcript_store.write_entry(
            session_id="cli-management",
            turn_id=trace_id,
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
            timestamp=datetime.now(timezone.utc),
            payload={"event": event_name, **payload},
            source="cli.adapter.closure",
            trace_id=trace_id,
        )

    def _read_cli_audit_entries(self, *, limit: int) -> List[Any]:
        if self._transcript_store is None:
            return []
        if hasattr(self._transcript_store, "list_entries"):
            return list(
                self._transcript_store.list_entries(
                    session_id=None,
                    entry_type=AuditEventType.PLUGIN_AUDIT_EVENT.value,
                    limit=limit,
                )
            )
        if hasattr(self._transcript_store, "read_entries"):
            return list(self._transcript_store.read_entries(session_id="cli-management") or [])
        return []

    def _write_invocation_audit(
        self,
        *,
        config: CliToolRegistrationConfig,
        result: CliInvocationResult,
        mapped_domain: str,
    ) -> None:
        if self._transcript_store is None:
            return
        self._transcript_store.write_entry(
            session_id="cli-management",
            turn_id=result.trace_id,
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
            timestamp=datetime.now(timezone.utc),
            payload={
                "tool_name": config.tool_name,
                "mapped_domain": mapped_domain,
                "read_only": config.read_only_flag,
                "side_effect_free": config.read_only_flag,
                "mutates_state": not config.read_only_flag,
                "requires_cloud_audit": not config.read_only_flag,
                **result.model_dump(mode="json"),
            },
            source="cli.adapter.test_call",
            trace_id=result.trace_id,
        )


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))
