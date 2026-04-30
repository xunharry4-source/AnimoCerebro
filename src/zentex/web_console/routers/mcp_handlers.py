from __future__ import annotations
"""
MCP Route Handlers — Business logic for Model Context Protocol interactions.
Extracted from mcp.py to follow the Facade-First / Thin-Route pattern.
"""
from typing import Any, List, Optional
from uuid import uuid4
from zentex.mcp.models import McpServerConfig, McpServerRuntimeState
from zentex.mcp.service import McpIntegrationService
from zentex.web_console.contracts.mcp import (
    McpServerStatusItem,
    McpServerToolItem,
    McpServerRegistrationRequest,
    McpToolTestCallResult,
    McpServerDetailItem,
    McpTaskSummary,
)


def handle_list_mcp_servers(service: McpIntegrationService) -> List[McpServerStatusItem]:
    """Handle listing and mapping MCP server states."""
    states: List[McpServerRuntimeState] = service.list_servers()
    return [
        McpServerStatusItem(
            server_id=state.server_id,
            transport_type=state.transport_type,
            status=state.status,
            tool_count=state.tool_count,
            error_message=state.error_message,
            tools=[
                McpServerToolItem(
                    tool_name=tool.tool_name,
                    description=tool.description,
                    mapped_domain=tool.mapped_domain,
                    mcp_id=tool.mcp_id,
                    feature_code=tool.feature_code,
                    execution_domain=tool.execution_domain,
                    read_only=tool.read_only,
                    side_effect_free=tool.side_effect_free,
                    mutates_state=tool.mutates_state,
                    requires_cloud_audit=tool.requires_cloud_audit,
                    status=tool.status,
                )
                for tool in state.tools
            ],
        )
        for state in states
    ]


def handle_register_mcp_server(
    payload: McpServerRegistrationRequest,
    service: McpIntegrationService,
) -> McpServerStatusItem:
    """Handle registering a new MCP server.

    Raises ValueError if the server cannot be reached (status == 'degraded').
    Registration is fail-closed: a degraded state means the health probe or
    tool-list failed, so the server should not be considered registered.
    """
    request_data = payload.model_dump(mode="json")
    inline_credential = request_data.pop("auth_credential", None)
    if inline_credential:
        credential_id = inline_credential.get("credential_id") or f"mcp-{payload.server_id}-{uuid4().hex[:12]}"
        service.store_server_credential(
            payload.server_id,
            credential_type=str(inline_credential["credential_type"]),
            secret_payload=dict(inline_credential["secret_payload"]),
            credential_id=credential_id,
            metadata=dict(inline_credential.get("metadata") or {}),
        )
        auth_config = dict(request_data.get("auth_config") or {})
        auth_config.setdefault("type", inline_credential["credential_type"])
        auth_config["credential_ref"] = credential_id
        request_data["auth_config"] = auth_config
        if request_data.get("auth_mode") == "none":
            request_data["auth_mode"] = "api_key" if inline_credential["credential_type"] == "api_key" else "bearer"

    service.register_server(McpServerConfig.model_validate(request_data))
    # Refresh and find the registered server
    states = handle_list_mcp_servers(service)
    registered = next((item for item in states if item.server_id == payload.server_id), None)
    if not registered:
        raise ValueError(f"Server {payload.server_id} registration failed or server not found after refresh.")
    if registered.status == "degraded":
        error_detail = registered.error_message or "health probe failed"
        raise ValueError(
            f"MCP server '{payload.server_id}' is not reachable: {error_detail}"
        )
    return registered


def handle_test_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: dict,
    service: McpIntegrationService,
) -> McpToolTestCallResult:
    """Handle testing an MCP tool call."""
    trace_id = f"mcp-test:{uuid4().hex}"
    result = service.test_call(
        server_id,
        tool_name=tool_name,
        arguments=arguments,
        trace_id=trace_id,
    )
    return McpToolTestCallResult(
        server_id=server_id,
        tool_name=tool_name,
        trace_id=trace_id,
        payload=result,
    )
