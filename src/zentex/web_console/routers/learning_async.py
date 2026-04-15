"""
Learning Async API Routes - 学习系统异步API路由

提供学习任务的提交、查询、取消等RESTful API端点。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from zentex.learning.directions import LearningDirection
from zentex.background_tasks import TaskStatus, TaskPriority

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["learning"])


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
# Dependency Injection
# ──────────────────────────────────────────────

def get_learning_async_service():
    """
    获取异步学习服务实例
    
    TODO: 实现完整的学习异步服务（类似反思的AsyncReflectionService）
    这里先提供基础框架
    """
    # 目前学习系统还没有完整的异步服务实现
    # 返回一个占位符，后续需要实现
    return None


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
    try:
        # 验证direction
        try:
            direction = LearningDirection(request.direction)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid direction: {request.direction}. "
                       f"Valid values: {[d.value for d in LearningDirection]}"
            )
        
        # 验证priority
        try:
            priority = TaskPriority[request.priority.upper()]
        except KeyError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority: {request.priority}. "
                       f"Valid values: {[p.name for p in TaskPriority]}"
            )
        
        # G16方向需要doc_url
        if direction == LearningDirection.G16_TOOL_SELF_STUDY and not request.doc_url:
            raise HTTPException(
                status_code=400,
                detail="G16_TOOL_SELF_STUDY direction requires doc_url"
            )
        
        # TODO: 调用实际的学习异步服务
        # 这里返回占位符响应
        import uuid
        task_id = str(uuid.uuid4())
        
        logger.info(f"Learning task started: {task_id} (direction={direction.value})")
        
        return StartLearningResponse(
            task_id=task_id,
            status="ACCEPTED",
            message="Learning task started. Note: Full async implementation pending.",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start learning task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/status", response_model=LearningTaskStatusResponse)
async def get_learning_task_status(task_id: str):
    """
    查询学习任务状态
    
    TODO: 实现完整的状态查询
    """
    # Placeholder implementation: check if ID exists (it doesn't in this sandbox)
    raise HTTPException(
        status_code=404, 
        detail=f"未找到学习任务: {task_id}，请检查任务 ID 是否正确。"
    )


@router.delete("/tasks/{task_id}")
async def cancel_learning_task(task_id: str):
    """
    取消学习任务
    
    TODO: 实现任务取消
    """
    # Placeholder implementation: check if ID exists
    raise HTTPException(
        status_code=404, 
        detail=f"无法取消任务：未找到学习任务 {task_id}"
    )


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
    # Stable placeholder: return empty list instead of 501
    return ListLearningTasksResponse(
        tasks=[],
        total=0,
        page=0,
        page_size=limit
    )


@router.get("/stats", response_model=LearningServiceStatsResponse)
async def get_learning_service_stats():
    """
    获取学习服务统计信息
    
    TODO: 实现统计信息
    """
    # Stable placeholder: 503 if monitoring not initialized
    raise HTTPException(
        status_code=503,
        detail="学习统计监控服务暂未上线，请稍后刷新"
    )


@router.get("/directions", response_model=AvailableDirectionsResponse)
async def get_available_directions():
    """
    获取可用的学习方向列表
    
    返回所有支持的学习方向及其描述。
    """
    try:
        from zentex.learning.engine import list_available_directions
        
        directions = list_available_directions()
        
        return AvailableDirectionsResponse(directions=directions)
    
    except Exception as e:
        logger.error(f"Failed to get available directions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
