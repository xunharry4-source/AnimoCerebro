from __future__ import annotations

from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from zentex.cli.service import CliIntegrationService
from zentex.cli.models import CliToolRegistrationConfig
from zentex.web_console.contracts.cli import (
    CliToolItem,
    CliToolRegistrationRequest,
    CliToolTestCallRequest,
    CliToolTestCallResult,
    CliToolDetailResponse,
    CliTaskSummary,
    CliExecutionHistory,
    CliCreditScore,
)
from zentex.web_console.dependencies import get_cli_service


router = APIRouter()


@router.get("/cli-tools", response_model=List[CliToolItem])
def list_cli_tools(service: CliIntegrationService = Depends(get_cli_service)) -> List[CliToolItem]:
    if service is None:
        raise HTTPException(status_code=503, detail="CLI service is not available")
    return [CliToolItem.model_validate(item.model_dump(mode="json")) for item in service.list_tools()]


@router.post("/cli-tools/register", response_model=CliToolItem)
def register_cli_tool(
    payload: CliToolRegistrationRequest,
    service: CliIntegrationService = Depends(get_cli_service),
) -> CliToolItem:
    if service is None:
        raise HTTPException(status_code=503, detail="CLI service is not available")
    try:
        state = service.register_tool(CliToolRegistrationConfig.model_validate(payload.model_dump(mode="json")))
        return CliToolItem.model_validate(state.model_dump(mode="json"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/cli-tools/{tool_name}/test-call", response_model=CliToolTestCallResult)
def test_cli_tool(
    tool_name: str,
    payload: CliToolTestCallRequest,
    service: CliIntegrationService = Depends(get_cli_service),
) -> CliToolTestCallResult:
    if service is None:
        raise HTTPException(status_code=503, detail="CLI service is not available")
    try:
        result = service.test_call(
            tool_name,
            arguments=payload.arguments,
            stdin_input=payload.stdin_input,
            working_directory=payload.working_directory,
            timeout_seconds=payload.timeout_seconds,
        )
        return CliToolTestCallResult.model_validate(result.model_dump(mode="json"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"CLI tool '{tool_name}' not registered") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Test call failed: {exc}") from exc


@router.get("/cli-tools/{tool_name}/detail", response_model=CliToolDetailResponse)
def get_cli_tool_detail(
    tool_name: str,
    service: CliIntegrationService = Depends(get_cli_service),
) -> CliToolDetailResponse:
    """获取 CLI 工具详细信息，包括信用分和任务统计"""
    if service is None:
        raise HTTPException(status_code=503, detail="CLI service is not available")
    
    tool = service.get_tool_detail(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"CLI tool '{tool_name}' not found")
    
    # 计算信用分
    credit_score_data = service.calculate_credit_score(tool_name)
    credit_score = CliCreditScore(**credit_score_data)
    
    # 获取任务统计
    task_stats = service.get_task_statistics(tool_name)
    
    # 构建响应
    return CliToolDetailResponse(
        command_name=tool.command_name,
        description=tool.description,
        mapped_domain=tool.mapped_domain,
        cli_id=tool.cli_id,
        feature_code=tool.feature_code,
        execution_domain=tool.execution_domain,
        read_only=tool.read_only,
        side_effect_free=tool.side_effect_free,
        mutates_state=tool.mutates_state,
        requires_cloud_audit=tool.requires_cloud_audit,
        status=tool.status,
        help_doc_url=tool.help_doc_url,
        project_path=tool.project_path,
        project_name=tool.project_name,
        project_description=tool.project_description,
        credit_score=credit_score,
        task_statistics=task_stats,
    )


@router.get("/cli-tools/{tool_name}/tasks/{status_filter}", response_model=List[CliTaskSummary])
def get_cli_tool_tasks(
    tool_name: str,
    status_filter: str,
    service: CliIntegrationService = Depends(get_cli_service),
) -> List[CliTaskSummary]:
    """获取 CLI 工具相关任务（按状态分类）"""
    if service is None:
        raise HTTPException(status_code=503, detail="CLI service is not available")
    
    # 验证状态过滤器
    valid_filters = ["in-progress", "pending", "failed"]
    if status_filter not in valid_filters:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status filter. Must be one of: {', '.join(valid_filters)}"
        )
    
    # 转换过滤器格式
    filter_map = {
        "in-progress": "in_progress",
        "pending": "pending",
        "failed": "failed"
    }
    
    tasks_data = service.get_tool_tasks_by_status(tool_name, filter_map[status_filter])
    
    # 转换为响应模型
    tasks = []
    for task_data in tasks_data:
        try:
            task = CliTaskSummary(
                task_id=task_data.get("task_id", ""),
                title=task_data.get("title", ""),
                status=task_data.get("status", "unknown"),
                created_at=task_data.get("created_at", ""),
                started_at=task_data.get("started_at"),
                completed_at=task_data.get("completed_at"),
                progress=task_data.get("progress", 0.0),
                priority=task_data.get("priority", "medium"),
                remarks=task_data.get("remarks"),
            )
            tasks.append(task)
        except Exception:
            # 跳过无法解析的任务
            continue
    
    return tasks


@router.get("/cli-tools/{tool_name}/execution-history", response_model=List[CliExecutionHistory])
def get_cli_tool_execution_history(
    tool_name: str,
    limit: int = 50,
    service: CliIntegrationService = Depends(get_cli_service),
) -> List[CliExecutionHistory]:
    """获取 CLI 工具执行历史记录"""
    if service is None:
        raise HTTPException(status_code=503, detail="CLI service is not available")
    
    # 限制最大数量
    limit = min(max(limit, 1), 200)
    
    history_data = service.get_tool_execution_history(tool_name, limit=limit)
    
    # 转换为响应模型
    history = []
    for entry_data in history_data:
        try:
            entry = CliExecutionHistory(**entry_data)
            history.append(entry)
        except Exception:
            # 跳过无法解析的记录
            continue
    
    return history
