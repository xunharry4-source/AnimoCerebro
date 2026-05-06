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

import shutil
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request

from zentex.agents.auth import AgentAuthError
from zentex.mcp.models import McpServerConfig
from zentex.mcp.service import McpIntegrationService, resolve_service
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
from .module_log_writer import record_module_management_log


router = APIRouter(tags=["mcp"])


def _mcp_missing_requirements(payload: McpServerRegistrationRequest) -> list[str]:
    if payload.transport_type != "stdio":
        return []
    command = payload.command.strip()
    requirements: list[str] = []
    if not command:
        return requirements
    resolved = shutil.which(command) if "/" not in command else command if shutil.which(command) else None
    if resolved is None:
        requirements.append(command)
    if command in {"npx", "npm", "node"} and shutil.which("node") is None:
        requirements.append("node")
    if command in {"npx", "npm"} and shutil.which("npm") is None:
        requirements.append("npm")
    return sorted(set(requirements))


def _mcp_registration_operator_message(payload: McpServerRegistrationRequest, message: str) -> str:
    missing = _mcp_missing_requirements(payload)
    if missing:
        return (
            f"MCP 注册失败：后端找不到或无法运行 {', '.join(missing)}。"
            "stdio MCP 需要先安装对应运行时/命令，例如 npx 类 MCP 需要 Node.js 18+ 和 npm；"
            "也可以改填后端进程 PATH 能找到的可执行文件绝对路径。"
        )
    if "MCP server health probe failed" in message or "is not reachable" in message:
        return (
            "MCP 注册失败：服务无法连通或健康检查失败。"
            "如果是 stdio MCP，请确认命令和运行时已安装；如果是 HTTP/SSE，请确认服务已启动且 URL 可访问。"
        )
    return message


def _mcp_registration_log_details(
    payload: McpServerRegistrationRequest,
    *,
    status: str | None = None,
    tool_count: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    auth_config = dict(payload.auth_config or {})
    auth_credential = payload.auth_credential
    auth_type = (
        str(auth_config.get("type") or "")
        or (str(auth_credential.credential_type) if auth_credential is not None else "")
        or payload.auth_mode
        or "none"
    )
    details: dict[str, Any] = {
        "server_id": payload.server_id,
        "transport_type": payload.transport_type,
        "command": payload.command,
        "args": payload.args,
        "scope": payload.scope,
        "auth_type": auth_type,
        "credential_ref": auth_config.get("credential_ref")
        or (auth_credential.credential_id if auth_credential is not None else None),
        "help_doc_url": payload.help_doc_url,
        "project_doc_url": payload.project_doc_url,
        "documentation_learning_required": payload.documentation_learning_required,
        "tool_bindings": payload.tool_bindings,
    }
    if status is not None:
        details["status"] = status
    if tool_count is not None:
        details["tool_count"] = tool_count
    if error is not None:
        details["error"] = error
    return {key: value for key, value in details.items() if value not in (None, "", [], {})}


def _record_mcp_registration_failure(
    request: Request,
    payload: McpServerRegistrationRequest,
    *,
    error: str,
) -> None:
    record_module_management_log(
        request,
        source_module="mcp",
        module_label="MCP 服务",
        action="register",
        action_label="注册失败",
        object_id=payload.server_id,
        before_status=None,
        after_status="failed",
        reason=f"MCP 注册失败：{error}",
        status="failed",
        details=_mcp_registration_log_details(payload, status="failed", error=error),
    )


def _require_mcp_service(request: Request) -> McpIntegrationService:
    """Fail-closed Depends wrapper: raise 503 when MCP service is not available."""
    service = resolve_service(get_mcp_service(request))
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


@router.get("/mcp-servers/statistics")
def get_mcp_server_statistics(
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> dict[str, Any]:
    return service.get_mcp_server_statistics()


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
    request: Request,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpServerStatusItem:
    try:
        item = handle_register_mcp_server(payload, service)
        record_module_management_log(
            request,
            source_module="mcp",
            module_label="MCP 服务",
            action="register",
            action_label="已注册",
            object_id=item.server_id,
            before_status=None,
            after_status=item.status,
            reason="通过 MCP 管理页注册新服务",
            details=_mcp_registration_log_details(
                payload,
                status=item.status,
                tool_count=item.tool_count,
            ),
        )
        return item
    except KeyError as exc:
        _record_mcp_registration_failure(request, payload, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        _record_mcp_registration_failure(request, payload, error=str(exc))
        missing_requirements = _mcp_missing_requirements(payload)
        detail: Any = str(exc)
        if missing_requirements or "is not reachable" in str(exc) or "health probe failed" in str(exc):
            detail = {
                "error": "mcp_runtime_missing" if missing_requirements else "mcp_unreachable",
                "error_code": "mcp_runtime_missing" if missing_requirements else "mcp_unreachable",
                "error_stage": "mcp_registration",
                "message": str(exc),
                "operator_message": _mcp_registration_operator_message(payload, str(exc)),
                "command": payload.command,
                "transport_type": payload.transport_type,
                "missing_requirements": missing_requirements,
            }
        raise HTTPException(status_code=400, detail=detail) from exc
    except AgentAuthError as exc:
        _record_mcp_registration_failure(request, payload, error=str(exc))
        raise HTTPException(
            status_code=400,
            detail={
                "error": "mcp_credential_vault_unavailable",
                "message": str(exc),
                "operator_message": (
                    "MCP 注册需要保存 API Key/Token，但凭证库未配置。"
                    "请先在 config/security.local.toml 中配置 [credential_vault].master_key，"
                    "或在 .env 中配置 CREDENTIAL_VAULT_MASTER_KEY，重启后端后再注册；"
                    "或者把认证方式改为“不需要认证”。"
                ),
            },
        ) from exc
    except ToolDocumentationLearningError as exc:
        _record_mcp_registration_failure(request, payload, error=str(exc))
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
    request: Request,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpServerStatusItem:
    try:
        before = next((item for item in handle_list_mcp_servers(service) if item.server_id == server_id), None)
        service.activate_server(server_id)
        item = next(item for item in handle_list_mcp_servers(service) if item.server_id == server_id)
        record_module_management_log(
            request,
            source_module="mcp",
            module_label="MCP 服务",
            action="status_change",
            action_label="已启用",
            object_id=server_id,
            before_status=getattr(before, "status", None),
            after_status=item.status,
            reason="操作员启用 MCP 服务，允许后续工具调用",
        )
        return item
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mcp-servers/{server_id}/disable", response_model=McpServerStatusItem)
def disable_mcp_server(
    server_id: str,
    request: Request,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> McpServerStatusItem:
    try:
        before = next((item for item in handle_list_mcp_servers(service) if item.server_id == server_id), None)
        service.disable_server(server_id)
        item = next(item for item in handle_list_mcp_servers(service) if item.server_id == server_id)
        record_module_management_log(
            request,
            source_module="mcp",
            module_label="MCP 服务",
            action="status_change",
            action_label="已停用",
            object_id=server_id,
            before_status=getattr(before, "status", None),
            after_status=item.status,
            reason="操作员停用 MCP 服务，后续任务不会再调度该服务",
        )
        return item
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/mcp-servers/{server_id}")
def delete_mcp_server(
    server_id: str,
    request: Request,
    service: McpIntegrationService = Depends(_require_mcp_service),
) -> dict[str, Any]:
    try:
        before = next((item for item in handle_list_mcp_servers(service) if item.server_id == server_id), None)
        success = service.delete_server(server_id)
        if success:
            record_module_management_log(
                request,
                source_module="mcp",
                module_label="MCP 服务",
                action="delete",
                action_label="已删除",
                object_id=server_id,
                before_status=getattr(before, "status", None),
                after_status="deleted",
                reason="操作员删除 MCP 服务注册记录",
            )
        return {"success": success, "server_id": server_id}
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
