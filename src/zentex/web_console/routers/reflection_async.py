"""
Reflection Async API Routes - 反思系统异步API路由

提供反思任务的提交、查询、取消等RESTful API端点。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from zentex.reflection.models import ReflectionType, ReflectionTrigger
from zentex.reflection.service import ReflectionService
from zentex.reflection.async_service import AsyncReflectionService
from zentex.background_tasks import TaskStatus, TaskPriority

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reflection", tags=["reflection"])


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
# Dependency Injection
# ──────────────────────────────────────────────

def get_async_reflection_service() -> AsyncReflectionService:
    """
    获取异步反思服务实例
    
    在实际应用中，这里应该从应用状态或依赖注入容器中获取
    """
    # TODO: 从app.state或DI容器获取
    # 这里为了演示，创建一个临时实例
    from zentex.reflection.service import ReflectionService
    
    sync_service = ReflectionService()
    async_service = AsyncReflectionService(
        reflection_service=sync_service,
        thread_pool_size=4,
        max_retries=3,
    )
    
    # 启动工作线程（如果尚未启动）
    if not async_service._worker_running:
        async_service.start_worker()
    
    return async_service


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@router.post("/generate", response_model=SubmitReflectionResponse)
async def submit_reflection_task(
    request: SubmitReflectionRequest,
    async_service: AsyncReflectionService = Depends(get_async_reflection_service),
):
    """
    提交反思任务（异步）
    
    立即返回task_id，任务在后台执行。
    可通过 GET /tasks/{task_id}/status 查询状态。
    """
    try:
        # 验证reflection_type
        try:
            reflection_type = ReflectionType(request.reflection_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reflection_type: {request.reflection_type}. "
                       f"Valid values: {[t.value for t in ReflectionType]}"
            )
        
        # 验证trigger
        try:
            trigger = ReflectionTrigger(request.trigger)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trigger: {request.trigger}"
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
        
        # 提交任务
        task_id = async_service.submit_reflection_task(
            subject=request.subject,
            reflection_type=reflection_type,
            context=request.context,
            trigger=trigger,
            priority=priority,
            trace_id=request.trace_id,
            session_id=request.session_id,
            template_id=request.template_id,
        )
        
        logger.info(f"Reflection task submitted: {task_id}")
        
        return SubmitReflectionResponse(
            task_id=task_id,
            status="ACCEPTED",
            message="Task submitted successfully. Use task_id to check status.",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit reflection task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    async_service: AsyncReflectionService = Depends(get_async_reflection_service),
):
    """
    查询任务状态
    
    返回任务的当前状态、进度、结果等信息。
    """
    try:
        status = async_service.get_task_status(task_id)
        
        if "error" in status and status["error"] == "Task not found":
            raise HTTPException(status_code=404, detail="Task not found")
        
        return TaskStatusResponse(**status)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    async_service: AsyncReflectionService = Depends(get_async_reflection_service),
):
    """
    取消任务
    
    仅可取消PENDING状态的任务。
    """
    try:
        success = async_service.cancel_task(task_id)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Cannot cancel task. Task may already be running or completed."
            )
        
        return {"success": True, "message": f"Task {task_id} cancelled"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", response_model=ListTasksResponse)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of tasks to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    async_service: AsyncReflectionService = Depends(get_async_reflection_service),
):
    """
    列出任务
    
    支持按状态过滤和分页。
    """
    try:
        # 解析status过滤器
        status_filter = None
        if status:
            try:
                status_filter = TaskStatus[status.upper()]
            except KeyError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. "
                           f"Valid values: {[s.name for s in TaskStatus]}"
                )
        
        # 获取任务列表
        tasks_data = async_service.list_tasks(
            status=status_filter,
            limit=limit,
            offset=offset,
        )
        
        # 转换为响应模型
        tasks = [TaskListItem(**task) for task in tasks_data]
        
        return ListTasksResponse(
            tasks=tasks,
            total=len(tasks_data),
            page=offset // limit + 1 if limit > 0 else 1,
            page_size=limit,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=ServiceStatsResponse)
async def get_service_stats(
    async_service: AsyncReflectionService = Depends(get_async_reflection_service),
):
    """
    获取服务统计信息
    
    返回监控器、执行器和队列的统计指标。
    """
    try:
        stats = async_service.get_stats()
        return ServiceStatsResponse(**stats)
    
    except Exception as e:
        logger.error(f"Failed to get service stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-generate")
async def batch_submit_reflection_tasks(
    requests: List[SubmitReflectionRequest],
    async_service: AsyncReflectionService = Depends(get_async_reflection_service),
):
    """
    批量提交反思任务
    
    一次性提交多个反思任务，返回所有task_id。
    """
    try:
        task_ids = []
        errors = []
        
        for i, request in enumerate(requests):
            try:
                # 验证reflection_type
                try:
                    reflection_type = ReflectionType(request.reflection_type)
                except ValueError:
                    errors.append({
                        "index": i,
                        "error": f"Invalid reflection_type: {request.reflection_type}"
                    })
                    continue
                
                # 验证trigger
                try:
                    trigger = ReflectionTrigger(request.trigger)
                except ValueError:
                    errors.append({
                        "index": i,
                        "error": f"Invalid trigger: {request.trigger}"
                    })
                    continue
                
                # 验证priority
                try:
                    priority = TaskPriority[request.priority.upper()]
                except KeyError:
                    errors.append({
                        "index": i,
                        "error": f"Invalid priority: {request.priority}"
                    })
                    continue
                
                # 提交任务
                task_id = async_service.submit_reflection_task(
                    subject=request.subject,
                    reflection_type=reflection_type,
                    context=request.context,
                    trigger=trigger,
                    priority=priority,
                    trace_id=request.trace_id,
                    session_id=request.session_id,
                    template_id=request.template_id,
                )
                
                task_ids.append(task_id)
            
            except Exception as e:
                errors.append({
                    "index": i,
                    "error": str(e)
                })
        
        return {
            "success_count": len(task_ids),
            "error_count": len(errors),
            "task_ids": task_ids,
            "errors": errors,
        }
    
    except Exception as e:
        logger.error(f"Failed to batch submit tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
