from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from zentex.plugins.contracts import PluginHealthStatus

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ModuleHealth:
    module_id: str
    module_name: str
    health_status: str
    status_message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    last_check_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class SystemHealthSnapshot:
    overall_health: str
    modules: List[ModuleHealth]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class SystemHealthService:
    """
    Centralized health monitoring service for the Zentex system.
    Relocated from web_console for zero-logic UI compliance.
    """
    
    def compute_overall_health(
        self,
        *,
        llm_service: Any = None,
        task_service: Any = None,
        memory_service: Any = None,
        kernel_facade: Any = None,
        foundation_service: Any = None
    ) -> SystemHealthSnapshot:
        """
        Aggregate health status from all major system components.
        """
        modules: List[ModuleHealth] = []
        
        # 1. LLM Health (from LLMService)
        if llm_service:
            try:
                llm_status = llm_service.get_detailed_status(probe_live=False)
                modules.append(ModuleHealth(
                    module_id="llm",
                    module_name="LLM Gateway",
                    health_status="healthy" if llm_status.available else "unhealthy",
                    status_message=llm_status.reason,
                    metrics={
                        "provider": llm_status.provider_name,
                        "health_probe": llm_status.health_status
                    }
                ))
            except Exception as e:
                modules.append(ModuleHealth(
                    module_id="llm",
                    module_name="LLM Gateway",
                    health_status="unhealthy",
                    status_message=f"LLM check failed: {e}"
                ))

        # 2. Memory Health
        if memory_service:
            try:
                # Optimized for core: check if service is responsive
                stats = {}
                if hasattr(memory_service, 'get_statistics'):
                    stats = memory_service.get_statistics()
                
                modules.append(ModuleHealth(
                    module_id="memory",
                    module_name="Memory Service",
                    health_status="healthy",
                    metrics={"total_records": stats.get("total_records", 0)}
                ))
            except Exception as e:
                modules.append(ModuleHealth(
                    module_id="memory",
                    module_name="Memory Service",
                    health_status="degraded",
                    status_message=str(e)
                ))

        # 3. Task Health
        if task_service:
            try:
                tasks = task_service.list_tasks() if hasattr(task_service, 'list_tasks') else []
                modules.append(ModuleHealth(
                    module_id="tasks",
                    module_name="Task Management",
                    health_status="healthy",
                    metrics={"total_tasks": len(tasks)}
                ))
            except Exception as e:
                 modules.append(ModuleHealth(
                    module_id="tasks",
                    module_name="Task Management",
                    health_status="degraded",
                    status_message=str(e)
                ))

        # Calculate overall
        unhealthy_count = sum(1 for m in modules if m.health_status == "unhealthy")
        degraded_count = sum(1 for m in modules if m.health_status == "degraded")
        
        if unhealthy_count > 0:
            overall = "unhealthy"
        elif degraded_count > 0:
            overall = "degraded"
        else:
            overall = "healthy"
            
        return SystemHealthSnapshot(
            overall_health=overall,
            modules=modules
        )

# Singleton factory
_instance: Optional[SystemHealthService] = None

def get_health_service() -> SystemHealthService:
    global _instance
    if _instance is None:
        _instance = SystemHealthService()
    return _instance
