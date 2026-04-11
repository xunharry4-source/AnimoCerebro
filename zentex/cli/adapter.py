from __future__ import annotations

"""CLI adapter that registers external shell tools behind Zentex plugin boundaries."""

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Protocol, Set
from uuid import uuid4

from pydantic import ConfigDict, PrivateAttr

from zentex.core.cli import CliInvocationResult, CliToolRegistrationConfig, CliToolRuntimeState
from zentex.core.cli import _MUTATING_TOKENS
from zentex.core.execution_registry import ExecutionDomainRegistry
from zentex.core.execution_spec import (
    ActionExecutionReceipt,
    ActionIntent,
    ActionStatus,
    ExecutionDomainPlugin,
)
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore

try:
    from plumbum import local as plumbum_local
except Exception:  # pragma: no cover - optional dependency
    plumbum_local = None

try:
    import pexpect
except Exception:  # pragma: no cover - optional dependency
    pexpect = None


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
    _transcript_store: BrainTranscriptStore = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: CliTransportClient,
        config: CliToolRegistrationConfig,
        transcript_store: BrainTranscriptStore,
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
            entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
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
    _transcript_store: BrainTranscriptStore = PrivateAttr()

    def attach_runtime(
        self,
        *,
        transport: CliTransportClient,
        config: CliToolRegistrationConfig,
        transcript_store: BrainTranscriptStore,
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
            entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
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
    _transcript_store: BrainTranscriptStore = PrivateAttr()
    _cognitive_registry: CognitiveToolRegistry = PrivateAttr()
    _execution_registry: ExecutionDomainRegistry = PrivateAttr()
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
        transcript_store: BrainTranscriptStore,
        cognitive_registry: CognitiveToolRegistry,
        execution_registry: ExecutionDomainRegistry,
    ) -> None:
        self._transport = transport
        self._transcript_store = transcript_store
        self._cognitive_registry = cognitive_registry
        self._execution_registry = execution_registry

    def register_tool(self, config: CliToolRegistrationConfig) -> CliToolRuntimeState:
        normalized = CliToolRegistrationConfig.model_validate(config.model_dump(mode="json"))
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
        state = self._register_tool_runtime(normalized)
        self._registered_tools[normalized.tool_name] = normalized
        self._tool_states[normalized.tool_name] = state
        return state

    def list_tool_states(self) -> List[CliToolRuntimeState]:
        return [self._tool_states[key] for key in sorted(self._tool_states.keys())]

    def get_tool_config(self, tool_name: str) -> CliToolRegistrationConfig:
        config = self._registered_tools.get(tool_name)
        if config is None:
            raise KeyError(tool_name)
        return config

    def invoke_tool(
        self,
        tool_name: str,
        *,
        arguments: List[str] | None = None,
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

    def _register_tool_runtime(self, config: CliToolRegistrationConfig) -> CliToolRuntimeState:
        plugin_id = f"cli:{config.tool_name}"
        feature_code = f"cli.{config.tool_name}"
        mapped_domain = "cognitive" if config.read_only_flag else "execution"
        if plugin_id not in self._registered_plugin_ids:
            if mapped_domain == "cognitive":
                plugin = CliCognitiveToolPlugin(
                    plugin_id=plugin_id,
                    version="1.0.0",
                    feature_code=feature_code,
                    is_concurrency_safe=True,
                    status=PluginLifecycleStatus.ACTIVE,
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
                plugin.attach_runtime(
                    transport=self._transport,
                    config=config,
                    transcript_store=self._transcript_store,
                )
                registration = self._cognitive_registry.register(plugin, description=config.description)
                if registration is None:
                    raise RuntimeError(f"Failed to register CLI cognitive tool: {plugin_id}")
                self._cognitive_registry.promote_plugin(plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "cli register")
                self._cognitive_registry.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, "cli register")
            else:
                plugin = CliExecutionDomainPlugin(
                    plugin_id=plugin_id,
                    version="1.0.0",
                    feature_code=feature_code,
                    is_concurrency_safe=False,
                    status=PluginLifecycleStatus.ACTIVE,
                    health_status=PluginHealthStatus.HEALTHY,
                    rollback_conditions=["cli_tool_regression"],
                    revocation_reasons=["cli_adapter_disabled"],
                    execution_domain=config.execution_domain,
                    requires_cloud_audit=True,
                )
                plugin.attach_runtime(
                    transport=self._transport,
                    config=config,
                    transcript_store=self._transcript_store,
                )
                registration = self._execution_registry.register(plugin, description=config.description)
                if registration is None:
                    raise RuntimeError(f"Failed to register CLI execution tool: {plugin_id}")
                self._execution_registry.promote_plugin(plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "cli register")
                self._execution_registry.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, "cli register")
            self._registered_plugin_ids.add(plugin_id)
        return CliToolRuntimeState(
            command_name=config.tool_name,
            description=config.description,
            mapped_domain=mapped_domain,
            plugin_id=plugin_id,
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
