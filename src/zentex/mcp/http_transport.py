from __future__ import annotations

from typing import Any

import requests

from zentex.mcp.models import McpServerConfig, McpToolDescriptor


class HttpJsonMcpTransportClient:
    """Minimal real HTTP transport for MCP-compatible JSON test servers.

    The transport intentionally uses HTTP requests and strict JSON parsing so
    bad JSON, empty responses, permission denials, timeouts, and disconnects
    surface as real transport failures instead of in-process shortcuts.
    """

    def __init__(self, *, timeout_seconds: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds

    def health_probe(self, config: McpServerConfig) -> bool:
        response = requests.get(f"{config.command.rstrip('/')}/health", timeout=self.timeout_seconds)
        return response.status_code == 200 and bool(response.json().get("ok"))

    def list_tools(self, config: McpServerConfig) -> list[McpToolDescriptor]:
        response = requests.get(f"{config.command.rstrip('/')}/tools", timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        tools = payload.get("tools")
        if not isinstance(tools, list):
            raise ValueError("MCP tools response must contain a tools list")
        return [McpToolDescriptor.model_validate(item) for item in tools]

    def invoke_tool(
        self,
        config: McpServerConfig,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        trace_id: str,
    ) -> dict[str, Any]:
        response = requests.post(
            f"{config.command.rstrip('/')}/tools/{tool_name}/call",
            json={"arguments": arguments, "trace_id": trace_id},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 403:
            raise PermissionError(response.text)
        response.raise_for_status()
        if not response.content:
            raise ValueError("empty MCP response")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("MCP tool response must be a JSON object")
        return payload
