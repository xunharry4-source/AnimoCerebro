from __future__ import annotations
"""
系统健康监控API路由

提供系统健康状态查询接口：
- GET /api/web/health/system - 获取系统整体健康状态

该端点不需要LLM配置，始终可用。
返回数据包括Token统计、Provider详情和各模块健康状态。
"""

from fastapi import APIRouter, Request

from zentex.web_console.contracts.health import SystemHealthPayload
from zentex.web_console.dependencies import (
    get_managed_plugin_records,
    get_kernel_service_facade,
)
from .health_handlers import handle_get_system_health


router = APIRouter()


@router.get("/health")
def get_health_simple(request: Request) -> dict:
    """Simple health check at /api/web/health for monitoring."""
    return {"status": "ok", "service": "Zentex Web Console"}


@router.get("/health/system", response_model=SystemHealthPayload)
def get_system_health(
    request: Request,
) -> SystemHealthPayload:
    """获取系统健康状态，包括Token统计、LLM请求统计和各功能模块健康"""
    managed_records = get_managed_plugin_records(request)
    kernel_facade = get_kernel_service_facade(request)
    
    return handle_get_system_health(
        request=request,
        managed_records=managed_records,
        kernel_facade=kernel_facade,
    )
