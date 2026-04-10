"""
系统健康监控服务

本模块提供系统健康状态收集和聚合功能，包括：
- 收集各功能模块的健康状态（LLM、Memory、Task、Plugin、Runtime、Session）
- 聚合Token使用统计和LLM Provider详情
- 计算整体系统健康评估

主要函数：
- build_system_health_payload(): 构建完整的系统健康响应
- build_token_usage_stats(): 聚合Token使用统计
- _get_module_health_status(): 获取单个模块的健康状态
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.web_console.contracts.health import (
    LLMProviderStats,
    ModuleHealthStatus,
    SystemHealthPayload,
    TokenUsageStats,
)
from zentex.web_console.contracts.plugins import ManagedPluginRecord


def _get_module_health_status(
    module_id: str,
    module_name: str,
    health_check_fn=None,
    metrics: Optional[Dict[str, Any]] = None,
) -> ModuleHealthStatus:
    """获取单个模块的健康状态"""
    try:
        if health_check_fn:
            status = health_check_fn()
            health_status = status.get("status", "unknown")
            status_message = status.get("message")
        else:
            health_status = "healthy"
            status_message = None
        
        return ModuleHealthStatus(
            module_id=module_id,
            module_name=module_name,
            health_status=health_status,
            status_message=status_message,
            last_check_at=datetime.now(timezone.utc).isoformat(),
            metrics=metrics or {},
        )
    except Exception as e:
        return ModuleHealthStatus(
            module_id=module_id,
            module_name=module_name,
            health_status="unhealthy",
            status_message=f"检查失败: {str(e)}",
            last_check_at=datetime.now(timezone.utc).isoformat(),
            metrics=metrics or {},
        )


def build_token_usage_stats(
    managed_records: Dict[str, ManagedPluginRecord],
    llm_gateway_stats: Optional[Dict[str, int]] = None,
) -> TokenUsageStats:
    """构建Token使用统计"""
    providers: List[LLMProviderStats] = []
    total_request_count = 0
    total_input_tokens = 0
    total_output_tokens = 0
    
    # 从managed records中获取provider统计
    for record in managed_records.values():
        plugin = record.plugin
        if not hasattr(plugin, 'provider_name'):
            continue
        
        # 尝试获取plugin的统计数据
        plugin_stats = {
            "request_count": getattr(plugin, "_request_count", 0),
            "input_tokens": getattr(plugin, "_input_tokens", 0),
            "output_tokens": getattr(plugin, "_output_tokens", 0),
        }
        
        request_count = plugin_stats["request_count"]
        input_tokens = plugin_stats["input_tokens"]
        output_tokens = plugin_stats["output_tokens"]
        total_tokens = input_tokens + output_tokens
        
        # 确定健康状态
        health_status_value = "unknown"
        if hasattr(plugin, 'health_status'):
            health_status_value = plugin.health_status.value if plugin.health_status else "unknown"
        
        provider_stat = LLMProviderStats(
            provider_name=str(getattr(plugin, 'provider_name', 'unknown')),
            api_base=str(getattr(plugin, 'api_base', '')) or None,
            health_status=health_status_value,
            request_count=request_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error_count=getattr(plugin, '_error_count', 0),
        )
        providers.append(provider_stat)
        
        total_request_count += request_count
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
    
    # 如果llm_gateway有统计数据，使用它作为总体统计
    if llm_gateway_stats:
        total_request_count = max(total_request_count, llm_gateway_stats.get("request_count", 0))
        total_input_tokens = max(total_input_tokens, llm_gateway_stats.get("input_tokens", 0))
        total_output_tokens = max(total_output_tokens, llm_gateway_stats.get("output_tokens", 0))
    
    total_tokens = total_input_tokens + total_output_tokens
    
    return TokenUsageStats(
        total_request_count=total_request_count,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_tokens=total_tokens,
        providers=providers,
    )


def build_system_health_payload(
    managed_records: Dict[str, ManagedPluginRecord],
    llm_gateway_stats: Optional[Dict[str, int]] = None,
    runtime: Optional[Any] = None,
    session: Optional[Any] = None,
) -> SystemHealthPayload:
    """构建系统健康状态负载"""
    
    # 收集各模块健康状态
    modules: List[ModuleHealthStatus] = []
    
    # 1. LLM Provider模块
    llm_providers = [
        record for record in managed_records.values()
        if hasattr(record.plugin, 'provider_name')
    ]
    if llm_providers:
        healthy_count = sum(
            1 for r in llm_providers 
            if getattr(r.plugin, 'health_status', None) == PluginHealthStatus.HEALTHY
        )
        total_count = len(llm_providers)
        
        if healthy_count == total_count:
            llm_health = "healthy"
            llm_message = f"{total_count}个Provider全部健康"
        elif healthy_count > 0:
            llm_health = "degraded"
            llm_message = f"{healthy_count}/{total_count}个Provider健康"
        else:
            llm_health = "unhealthy"
            llm_message = "所有Provider都不健康"
        
        modules.append(ModuleHealthStatus(
            module_id="llm_providers",
            module_name="LLM Providers",
            health_status=llm_health,
            status_message=llm_message,
            last_check_at=datetime.now(timezone.utc).isoformat(),
            metrics={
                "total_providers": total_count,
                "healthy_providers": healthy_count,
            },
        ))
    
    # 2. Memory模块
    memory_service = None
    if runtime and hasattr(runtime, 'runtime_memory_store'):
        memory_service = runtime.runtime_memory_store
    elif session and hasattr(session, 'memory_store'):
        memory_service = session.memory_store
    
    if memory_service:
        try:
            memory_overview = memory_service.get_overview() if hasattr(memory_service, 'get_overview') else {}
            modules.append(_get_module_health_status(
                module_id="memory",
                module_name="Memory Service",
                health_check_fn=lambda: {"status": "healthy"},
                metrics={
                    "total_records": memory_overview.get("total_records", 0) if isinstance(memory_overview, dict) else 0,
                },
            ))
        except Exception:
            modules.append(_get_module_health_status(
                module_id="memory",
                module_name="Memory Service",
                health_check_fn=lambda: {"status": "degraded", "message": "无法获取内存服务状态"},
            ))
    
    # 3. Task模块
    if runtime and hasattr(runtime, 'task_service'):
        task_service = runtime.task_service
        try:
            tasks = task_service.list_tasks() if hasattr(task_service, 'list_tasks') else []
            active_tasks = len([t for t in tasks if hasattr(t, 'status') and str(t.status) == "active"])
            modules.append(_get_module_health_status(
                module_id="tasks",
                module_name="Task Management",
                health_check_fn=lambda: {"status": "healthy"},
                metrics={
                    "total_tasks": len(tasks),
                    "active_tasks": active_tasks,
                },
            ))
        except Exception:
            modules.append(_get_module_health_status(
                module_id="tasks",
                module_name="Task Management",
                health_check_fn=lambda: {"status": "degraded"},
            ))
    
    # 4. Plugin Registry模块
    plugin_registry = None
    if runtime and hasattr(runtime, 'cognitive_tool_registry'):
        plugin_registry = runtime.cognitive_tool_registry
    
    if plugin_registry:
        try:
            plugins_info = plugin_registry.list_plugins() if hasattr(plugin_registry, 'list_plugins') else []
            active_plugins = len([p for p in plugins_info if hasattr(p, 'status') and str(p.status) == "active"])
            modules.append(_get_module_health_status(
                module_id="plugins",
                module_name="Plugin Registry",
                health_check_fn=lambda: {"status": "healthy"},
                metrics={
                    "total_plugins": len(plugins_info),
                    "active_plugins": active_plugins,
                },
            ))
        except Exception:
            modules.append(_get_module_health_status(
                module_id="plugins",
                module_name="Plugin Registry",
                health_check_fn=lambda: {"status": "degraded"},
            ))
    
    # 5. Runtime模块
    if runtime:
        try:
            runtime_state = runtime.get_runtime_state() if hasattr(runtime, 'get_runtime_state') else None
            if runtime_state:
                modules.append(_get_module_health_status(
                    module_id="runtime",
                    module_name="Brain Runtime",
                    health_check_fn=lambda: {"status": "healthy"},
                    metrics={
                        "runtime_id": runtime_state.runtime_id,
                        "active_sessions": len(runtime_state.active_session_ids),
                        "degraded_mode": runtime_state.degraded_mode,
                    },
                ))
        except Exception:
            modules.append(_get_module_health_status(
                module_id="runtime",
                module_name="Brain Runtime",
                health_check_fn=lambda: {"status": "degraded"},
            ))
    
    # 6. Session模块
    if session:
        try:
            snapshot = session.get_snapshot() if hasattr(session, 'get_snapshot') else None
            if snapshot:
                modules.append(_get_module_health_status(
                    module_id="session",
                    module_name="Active Session",
                    health_check_fn=lambda: {"status": "healthy"},
                    metrics={
                        "session_id": snapshot.session_id,
                        "turn_count": snapshot.turn_count,
                        "current_reasoning_mode": getattr(snapshot, 'current_reasoning_mode', None),
                    },
                ))
        except Exception:
            modules.append(_get_module_health_status(
                module_id="session",
                module_name="Active Session",
                health_check_fn=lambda: {"status": "degraded"},
            ))
    
    # 计算整体健康状态
    unhealthy_count = sum(1 for m in modules if m.health_status == "unhealthy")
    degraded_count = sum(1 for m in modules if m.health_status == "degraded")
    
    if unhealthy_count > 0:
        overall_health = "unhealthy"
    elif degraded_count > 0:
        overall_health = "degraded"
    else:
        overall_health = "healthy"
    
    # 构建Token使用统计
    token_usage = build_token_usage_stats(managed_records, llm_gateway_stats)
    
    return SystemHealthPayload(
        overall_health=overall_health,
        token_usage=token_usage,
        modules=modules,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
