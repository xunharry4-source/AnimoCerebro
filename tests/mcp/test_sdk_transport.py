from __future__ import annotations

from pathlib import Path
import sys
import textwrap

import pytest

from zentex.core.mcp import McpServerConfig
from zentex.mcp.sdk_transport import OfficialMcpSdkTransportClient


@pytest.mark.skipif(sys.platform == "win32", reason="stdio MCP test script assumes POSIX-like process semantics")
def test_official_sdk_transport_lists_and_invokes_stdio_tool(tmp_path: Path) -> None:
    server_script = tmp_path / "mcp_echo_server.py"
    server_script.write_text(
        textwrap.dedent(
            """
            from mcp.server.fastmcp import FastMCP

            app = FastMCP("EchoServer")

            @app.tool()
            def echo(text: str) -> str:
                return f"echo:{text}"

            if __name__ == "__main__":
                app.run("stdio")
            """
        ),
        encoding="utf-8",
    )
    config = McpServerConfig(
        server_id="echo-server",
        transport_type="stdio",
        command=sys.executable,
        args=[str(server_script)],
    )

    transport = OfficialMcpSdkTransportClient()

    tools = transport.list_tools(config)
    assert len(tools) == 1
    assert tools[0].tool_name == "echo"

    result = transport.invoke_tool(
        config,
        tool_name="echo",
        arguments={"text": "hello"},
        trace_id="trace-sdk-echo",
    )
    assert result["isError"] is False
    assert result["content"][0]["text"] == "echo:hello"
