from __future__ import annotations

"""Optional official MCP SDK transport for real stdio/SSE server interaction."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from threading import Thread
from typing import Any, AsyncIterator, Dict, List, Protocol

from zentex.mcp.models import McpServerConfig, McpToolDescriptor

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client
except Exception:  # pragma: no cover - optional dependency
    ClientSession = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    sse_client = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]
    streamablehttp_client = None  # type: ignore[assignment]


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


def _run_async_from_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            result["error"] = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


class OfficialMcpSdkTransportClient(McpTransportClient):
    """Transport backed by the official MCP Python SDK."""

    def __init__(self) -> None:
        if ClientSession is None or stdio_client is None or StdioServerParameters is None:
            raise ModuleNotFoundError("mcp")

    def list_tools(self, config: McpServerConfig) -> List[McpToolDescriptor]:
        return _run_async_from_sync(self._list_tools(config))

    def invoke_tool(
        self,
        config: McpServerConfig,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        return _run_async_from_sync(self._invoke_tool(config, tool_name=tool_name, arguments=arguments, trace_id=trace_id))

    def health_probe(self, config: McpServerConfig) -> bool:
        _run_async_from_sync(self._list_tools(config))
        return True

    async def _list_tools(self, config: McpServerConfig) -> List[McpToolDescriptor]:
        async with self._session(config) as session:
            result = await session.list_tools()
            return [
                McpToolDescriptor(
                    tool_name=tool.name,
                    description=tool.description or tool.name,
                    input_schema=getattr(tool, "inputSchema", {}) or {},
                    mutates_state=not bool(getattr(tool, "annotations", None) and getattr(tool.annotations, "readOnlyHint", False)),
                    read_only_hint=bool(getattr(tool, "annotations", None) and getattr(tool.annotations, "readOnlyHint", False)),
                )
                for tool in result.tools
            ]

    async def _invoke_tool(
        self,
        config: McpServerConfig,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        async with self._session(config) as session:
            result = await session.call_tool(
                tool_name,
                arguments=arguments,
                read_timeout_seconds=timedelta(seconds=30),
                meta={"trace_id": trace_id},
            )
            payload = result.model_dump(mode="json")
            payload.setdefault("summary", f"{tool_name} completed")
            return payload

    @asynccontextmanager
    async def _session(self, config: McpServerConfig) -> AsyncIterator[ClientSession]:
        headers = dict(config.env) or None
        if config.transport_type == "stdio":
            server = StdioServerParameters(
                command=config.command,
                args=list(config.args),
                env=headers,
                cwd=None,
            )
            async with stdio_client(server) as (read_stream, write_stream):
                session = ClientSession(read_stream, write_stream)
                async with session:
                    await session.initialize()
                    yield session
            return
        if config.transport_type == "sse":
            if sse_client is None:
                raise ModuleNotFoundError("mcp")
            async with sse_client(config.command, headers=headers) as (read_stream, write_stream):
                session = ClientSession(read_stream, write_stream)
                async with session:
                    await session.initialize()
                    yield session
            return
        if config.transport_type in {"http", "streamable_http"}:
            if streamablehttp_client is None:
                raise ModuleNotFoundError("mcp")
            async with streamablehttp_client(config.command, headers=headers) as (
                read_stream,
                write_stream,
                _get_session_id,
            ):
                session = ClientSession(read_stream, write_stream)
                async with session:
                    await session.initialize()
                    yield session
            return
        raise ValueError(f"Unsupported MCP transport: {config.transport_type}")


def build_official_mcp_client_factory() -> Any:
    """Return a client factory compatible with McpAdapterPlugin.attach_runtime()."""

    def _factory(config: McpServerConfig) -> OfficialMcpSdkTransportClient:
        _ = config
        return OfficialMcpSdkTransportClient()

    return _factory
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
