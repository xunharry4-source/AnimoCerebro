"""
Reflection Async API Routes - 反思系统异步API路由

提供反思任务的提交、查询、取消等RESTful API端点。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reflection", tags=["reflection"])


def _web_console_async_reflection_removed() -> HTTPException:
    return HTTPException(
        status_code=410,
        detail={
            "error": "web_console_async_reflection_removed",
            "message": "web-console 不再承接 reflection async 调度；请从后台 reflection service 直接调用。",
        },
    )


# ──────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────

class SubmitReflectionRequest(BaseModel):
    """提交反思任务请求"""
    subject: str = Field(..., min_length=1, description="反思主题")
    reflection_type: str = Field(..., description="反思类型")
    context: Dict[str, Any] = Field(default_factory=dict, description="反思上下文")
    trigger: str = Field(default="automatic", description="触发器")
    priority: str = Field(default="NORMAL", description="优先级: CRITICAL/HIGH/NORMAL/LOW")
    trace_id: Optional[str] = Field(None, description="追踪ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    template_id: Optional[str] = Field(None, description="模板ID")


class SubmitReflectionResponse(BaseModel):
    """提交反思任务响应"""
    task_id: str
    status: str = "ACCEPTED"
    message: str = "Task submitted successfully"


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    progress: float
    retry_count: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class TaskListItem(BaseModel):
    """任务列表项"""
    task_id: str
    task_type: str
    subtype: Optional[str] = None
    status: str
    priority: int
    progress: float
    retry_count: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None


class ListTasksResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskListItem]
    total: int
    page: int
    page_size: int


class ServiceStatsResponse(BaseModel):
    """服务统计响应"""
    monitor: Dict[str, Any]
    executor: Dict[str, Any]
    queue: Dict[str, Any]


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@router.post("/generate", response_model=SubmitReflectionResponse)
async def submit_reflection_task(
    request: SubmitReflectionRequest,
):
    """
    提交反思任务（异步）
    
    立即返回task_id，任务在后台执行。
    可通过 GET /tasks/{task_id}/status 查询状态。
    """
    raise _web_console_async_reflection_removed()


@router.get("/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
):
    """
    查询任务状态
    
    返回任务的当前状态、进度、结果等信息。
    """
    raise _web_console_async_reflection_removed()


@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
):
    """
    取消任务
    
    仅可取消PENDING状态的任务。
    """
    raise _web_console_async_reflection_removed()


@router.get("/tasks", response_model=ListTasksResponse)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of tasks to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
):
    """
    列出任务
    
    支持按状态过滤和分页。
    """
    raise _web_console_async_reflection_removed()


@router.get("/stats", response_model=ServiceStatsResponse)
async def get_service_stats(
):
    """
    获取服务统计信息
    
    返回监控器、执行器和队列的统计指标。
    """
    raise _web_console_async_reflection_removed()


@router.post("/batch-generate")
async def batch_submit_reflection_tasks(
    requests: List[SubmitReflectionRequest],
):
    """
    批量提交反思任务
    
    一次性提交多个反思任务，返回所有task_id。
    """
    raise _web_console_async_reflection_removed()
