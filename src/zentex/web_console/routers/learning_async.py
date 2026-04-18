"""
Learning Async API Routes - 学习系统异步API路由

提供学习任务的提交、查询、取消等RESTful API端点。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["learning"])


def _web_console_async_learning_removed() -> HTTPException:
    return HTTPException(
        status_code=410,
        detail={
            "error": "web_console_async_learning_removed",
            "message": "web-console 不再承接 learning async 调度；请从后台学习服务直接调用。",
        },
    )


# ──────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────

class StartLearningRequest(BaseModel):
    """启动学习任务请求"""
    direction: str = Field(..., description="学习方向")
    doc_url: Optional[str] = Field(None, description="文档URL (G16必需)")
    priority: str = Field(default="NORMAL", description="优先级: CRITICAL/HIGH/NORMAL/LOW")
    dry_run: bool = Field(default=False, description="是否为模拟运行")
    extra_context: Optional[Dict[str, Any]] = Field(None, description="额外上下文")


class StartLearningResponse(BaseModel):
    """启动学习任务响应"""
    task_id: str
    status: str = "ACCEPTED"
    message: str = "Learning task started successfully"


class LearningTaskStatusResponse(BaseModel):
    """学习任务状态响应"""
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


class LearningTaskListItem(BaseModel):
    """学习任务列表项"""
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


class ListLearningTasksResponse(BaseModel):
    """学习任务列表响应"""
    tasks: List[LearningTaskListItem]
    total: int
    page: int
    page_size: int


class LearningServiceStatsResponse(BaseModel):
    """学习服务统计响应"""
    monitor: Dict[str, Any]
    executor: Dict[str, Any]
    queue: Dict[str, Any]


class AvailableDirectionsResponse(BaseModel):
    """可用学习方向响应"""
    directions: List[Dict[str, Any]]


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@router.post("/start", response_model=StartLearningResponse)
async def start_learning_task(
    request: StartLearningRequest,
):
    """
    启动学习任务（异步）
    
    立即返回task_id，任务在后台执行。
    """
    raise _web_console_async_learning_removed()


@router.get("/tasks/{task_id}/status", response_model=LearningTaskStatusResponse)
async def get_learning_task_status(task_id: str):
    """
    查询学习任务状态
    
    TODO: 实现完整的状态查询
    """
    # Placeholder implementation: check if ID exists (it doesn't in this sandbox)
    raise _web_console_async_learning_removed()


@router.delete("/tasks/{task_id}")
async def cancel_learning_task(task_id: str):
    """
    取消学习任务
    
    TODO: 实现任务取消
    """
    # Placeholder implementation: check if ID exists
    raise _web_console_async_learning_removed()


@router.get("/tasks", response_model=ListLearningTasksResponse)
async def list_learning_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    列出学习任务
    
    TODO: 实现任务列表
    """
    raise _web_console_async_learning_removed()


@router.get("/stats", response_model=LearningServiceStatsResponse)
async def get_learning_service_stats():
    """
    获取学习服务统计信息
    
    TODO: 实现统计信息
    """
    raise _web_console_async_learning_removed()


@router.get("/directions", response_model=AvailableDirectionsResponse)
async def get_available_directions():
    """
    获取可用的学习方向列表
    
    返回所有支持的学习方向及其描述。
    """
    raise _web_console_async_learning_removed()
