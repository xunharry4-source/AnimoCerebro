from __future__ import annotations

"""Public MCP integration facade used by external callers."""

from typing import Any, Dict, List
from uuid import uuid4

from zentex.core.mcp import McpServerConfig, McpServerRuntimeState
from zentex.mcp.adapter import McpAdapterPlugin


class McpIntegrationService:
    def __init__(self, adapter: McpAdapterPlugin) -> None:
        self._adapter = adapter

    def list_servers(self) -> List[McpServerRuntimeState]:
        return self._adapter.list_server_states()

    def register_server(self, config: McpServerConfig) -> McpServerRuntimeState:
        return self._adapter.register_server(config)

    def test_call(
        self,
        server_id: str,
        *,
        tool_name: str,
        arguments: Dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Dict[str, Any]:
        return self._adapter.invoke_tool(
            server_id,
            tool_name=tool_name,
            arguments=dict(arguments or {}),
            trace_id=trace_id or f"mcp-test:{uuid4().hex}",
        )
