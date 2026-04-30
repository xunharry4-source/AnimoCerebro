"""
MCP Router — /api/web/mcp-servers endpoints.

RESPONSIBILITY:
  Exposes MCP (Model Context Protocol) server management: list, register,
  test-call, detail, and task listing.

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  get_mcp_service() returns None when app.state.runtime is not attached.
  _require_mcp_service() wraps it as a Depends guard and raises 503 explicitly
  so callers always receive a structured error, never AttributeError.

DOES NOT:
  - Own MCP server lifecycle (that is McpIntegrationService's job).
  - Manage app state or startup lifecycle.
"""

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from zentex.mcp.models import McpServerConfig
from zentex.mcp.service import McpIntegrationService
from zentex.tools.documentation_learning import ToolDocumentationLearningError
from zentex.web_console.contracts.mcp import (
    McpServerDetailItem,
    McpServerRegistrationRequest,
    McpServerStatusItem,
    McpTaskSummary,
    McpToolTestCallRequest,
    McpToolTestCallResult,
    ToolUsageProfile,
)
from zentex.web_console.dependencies import get_mcp_service
from .mcp_handlers import (
    handle_list_mcp_servers,
    handle_register_mcp_server,
    handle_test_mcp_tool,
)


router = APIRouter(tags=["mcp"])


def _require_mcp_service(service: Any = Depends(get_mcp_service)) -> McpIntegrationService:
    """Fail-closed Depends wrapper: raise 503 when MCP service is not available."""
    if service is None or getattr(service, "_is_stub", False):
        health = service.health_check() if service is not None and callable(getattr(service, "health_check", None)) else {}
        unavailable_reason = health.get("error") or "McpIntegrationService 未初始化，MCP 功能不可用。"
        raise HTTPException(
            status_code=503,
            detail={
                "error": "mcp_service_unavailable",
                "message": "McpIntegrationService 未初始化，MCP 功能不可用。",
                "developer_message": unavailable_reason,
            },
        )
    return service


@router.get("/mcp-servers", response_model=List[McpServerStatusItem])
def list_mcp_servers(
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> List[McpServerStatusItem]:
    return handle_list_mcp_servers(service)


@router.get("/mcp-servers/closure/diagnostics")
def diagnose_mcp_management_closure(
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> dict[str, Any]:
    return service.diagnose_mcp_management_closure()


@router.post("/mcp-servers/closure/fault-injection")
def run_mcp_fault_injection_matrix(
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> dict[str, Any]:
    return service.run_mcp_fault_injection_matrix()


@router.post("/mcp-servers/register", response_model=McpServerStatusItem)
def register_mcp_server(
    payload: McpServerRegistrationRequest,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpServerStatusItem:
    try:
        return handle_register_mcp_server(payload, service)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ToolDocumentationLearningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mcp-servers/{server_id}/health")
def get_mcp_server_health(
    server_id: str,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> dict[str, Any]:
    try:
        return service.get_server_health(server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mcp-servers/{server_id}/activate", response_model=McpServerStatusItem)
def activate_mcp_server(
    server_id: str,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpServerStatusItem:
    try:
        service.activate_server(server_id)
        return next(item for item in handle_list_mcp_servers(service) if item.server_id == server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mcp-servers/{server_id}/disable", response_model=McpServerStatusItem)
def disable_mcp_server(
    server_id: str,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpServerStatusItem:
    try:
        service.disable_server(server_id)
        return next(item for item in handle_list_mcp_servers(service) if item.server_id == server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/mcp-servers/{server_id}")
def delete_mcp_server(
    server_id: str,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> dict[str, Any]:
    try:
        return {"success": service.delete_server(server_id), "server_id": server_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mcp-servers/{server_id}/test-call", response_model=McpToolTestCallResult)
def test_mcp_tool(
    server_id: str,
    payload: McpToolTestCallRequest,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpToolTestCallResult:
    try:
        return handle_test_mcp_tool(
            server_id=server_id,
            tool_name=payload.tool_name,
            arguments=payload.arguments,
            service=service,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mcp-servers/{server_id}/tools/{tool_name}/usage-profile", response_model=ToolUsageProfile)
def get_mcp_tool_usage_profile(
    server_id: str,
    tool_name: str,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> ToolUsageProfile:
    try:
        return ToolUsageProfile.model_validate(
            service.get_tool_usage_profile(server_id, tool_name).model_dump(mode="json")
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Usage profile for MCP tool '{server_id}/{tool_name}' not found",
        ) from exc


@router.get("/mcp-servers/{server_id}", response_model=McpServerDetailItem)
def get_mcp_server_detail(
    server_id: str,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpServerDetailItem:
    try:
        return service.get_server_detail(server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mcp-servers/{server_id}/tasks", response_model=List[McpTaskSummary])
def list_mcp_server_tasks(
    server_id: str,
    status: Optional[str] = None,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> List[McpTaskSummary]:
    return service.list_server_tasks(server_id, status=status)
