"""
系统健康监控API路由

提供系统健康状态查询接口：
- GET /api/web/health/system - 获取系统整体健康状态

该端点不需要LLM配置，始终可用。
返回数据包括Token统计、Provider详情和各模块健康状态。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from zentex.web_console.contracts.health import SystemHealthPayload
from zentex.web_console.dependencies import get_managed_plugin_records
from zentex.web_console.services.health import build_system_health_payload


router = APIRouter()


@router.get("/health/system", response_model=SystemHealthPayload)
def get_system_health(
    request: Request,
) -> SystemHealthPayload:
    """获取系统健康状态，包括Token统计、LLM请求统计和各功能模块健康"""
    from zentex.web_console.dependencies import get_managed_plugin_records
    managed_records = get_managed_plugin_records(request)
    
    # 尝试从request.app获取runtime和session
    runtime = getattr(request.app.state, 'runtime', None)
    session = getattr(request.app.state, 'session', None)
    
    # 尝试从 runtime 获取 LLM gateway 统计
    llm_gateway_stats = None
    if runtime and hasattr(runtime, 'llm_gateway'):
        try:
            llm_gateway_stats = runtime.llm_gateway.stats_snapshot()
        except Exception:
            pass
    
    from zentex.web_console.services.health import build_system_health_payload
    return build_system_health_payload(
        managed_records=managed_records,
        llm_gateway_stats=llm_gateway_stats,
        runtime=runtime,
        session=session,
    )
