"""
System Health Service Thin Adapter — Web Console Layer.

ARCHITECTURE ROLE:
1. Thin Facade: Directs API requests to core domain services (SystemHealthService, LLMService).
2. Zero Business Logic: Strictly prohibited from implementing health aggregation rules or status scoring.
3. Responsibility:
   - [Query Condition Preparation]: Validating and packaging dependency services for core health assessment.
   - [Result Splicing]: Mapping technical health snapshots into the SystemHealthPayload API contract.

DECOUPLING POLICY (Zentex Codex §2):
This module must remain a 'Logic-Free Zone'. Any evolution of health check algorithms, 
module categorization, or status threshold rules must be implemented in `zentex.system.health`.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zentex.system.health import get_health_service
from zentex.llm.service import get_llm_service
from zentex.web_console.contracts.health import (
    LLMProviderStats,
    ModuleHealthStatus,
    SystemHealthPayload,
    TokenUsageStats,
)

def build_system_health_payload(
    managed_records: Dict[str, Any],
    llm_gateway_stats: Optional[Dict[str, int]] = None,
    kernel_facade: Optional[Any] = None,
    foundation_service: Optional[Any] = None,
    task_service: Optional[Any] = None,
    memory_service: Optional[Any] = None,
) -> SystemHealthPayload:
    """
    Thin adapter for core health aggregation.
    Zero business logic: only orchestrates data retrieval and splicing.
    """
    health_service = get_health_service()
    llm_service = get_llm_service()
    
    # 1. Retrieve aggregated usage from core (Result Splicing)
    usage_data = llm_service.get_aggregated_usage_stats()
    token_usage = TokenUsageStats(
        total_request_count=usage_data["total_request_count"],
        total_input_tokens=usage_data["total_input_tokens"],
        total_output_tokens=usage_data["total_output_tokens"],
        total_tokens=usage_data["total_tokens"],
        providers=[LLMProviderStats(**p) for p in usage_data["providers"]]
    )
    
    # 2. Retrieve overall system health from core
    snapshot = health_service.compute_overall_health(
        llm_service=llm_service,
        task_service=task_service,
        memory_service=memory_service,
        kernel_facade=kernel_facade,
        foundation_service=foundation_service
    )
    
    # 3. Final Result Splicing into UI Contract
    return SystemHealthPayload(
        overall_health=snapshot.overall_health,
        token_usage=token_usage,
        modules=[
            ModuleHealthStatus(
                module_id=m.module_id,
                module_name=m.module_name,
                health_status=m.health_status,
                status_message=m.status_message,
                last_check_at=m.last_check_at.isoformat(),
                metrics=m.metrics
            ) for m in snapshot.modules
        ],
        timestamp=snapshot.timestamp.isoformat()
    )
