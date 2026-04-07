from __future__ import annotations

"""Public CLI integration facade used by web and runtime callers."""

from typing import List, Optional

from zentex.cli.adapter import CliAdapterPlugin
from zentex.core.cli import CliInvocationResult, CliToolRegistrationConfig, CliToolRuntimeState


class CliIntegrationService:
    def __init__(self, adapter: CliAdapterPlugin) -> None:
        self._adapter = adapter

    def list_tools(self) -> List[CliToolRuntimeState]:
        return self._adapter.list_tool_states()

    def register_tool(self, config: CliToolRegistrationConfig) -> CliToolRuntimeState:
        return self._adapter.register_tool(config)

    def test_call(
        self,
        tool_name: str,
        *,
        arguments: List[str] | None = None,
        stdin_input: Optional[str] = None,
        working_directory: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> CliInvocationResult:
        return self._adapter.invoke_tool(
            tool_name,
            arguments=arguments,
            stdin_input=stdin_input,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
