from __future__ import annotations
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends

from zentex.core.mcp import McpServerConfig, McpServerRuntimeState
from zentex.mcp.service import McpIntegrationService
from zentex.web_console.contracts.mcp import (
    McpServerRegistrationRequest,
    McpServerStatusItem,
    McpServerToolItem,
    McpToolTestCallRequest,
    McpToolTestCallResult,
)
from zentex.web_console.dependencies import get_mcp_service


router = APIRouter()


@router.get("/mcp-servers", response_model=List[McpServerStatusItem])
def list_mcp_servers(service: McpIntegrationService = Depends(get_mcp_service)) -> List[McpServerStatusItem]:
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
                    plugin_id=tool.plugin_id,
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


@router.post("/mcp-servers/register", response_model=McpServerStatusItem)
def register_mcp_server(
    payload: McpServerRegistrationRequest,
    service: McpIntegrationService = Depends(get_mcp_service),
) -> McpServerStatusItem:
    service.register_server(McpServerConfig.model_validate(payload.model_dump(mode="json")))
    registered = next(item for item in list_mcp_servers(service) if item.server_id == payload.server_id)
    return registered


@router.post("/mcp-servers/{server_id}/test-call", response_model=McpToolTestCallResult)
def test_mcp_tool(
    server_id: str,
    payload: McpToolTestCallRequest,
    service: McpIntegrationService = Depends(get_mcp_service),
) -> McpToolTestCallResult:
    trace_id = f"mcp-test:{uuid4().hex}"
    result = service.test_call(
        server_id,
        tool_name=payload.tool_name,
        arguments=payload.arguments,
        trace_id=trace_id,
    )
    return McpToolTestCallResult(
        server_id=server_id,
        tool_name=payload.tool_name,
        trace_id=trace_id,
        payload=result,
    )
