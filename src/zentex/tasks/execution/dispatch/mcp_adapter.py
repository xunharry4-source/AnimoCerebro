from __future__ import annotations

from typing import Any, Dict


async def execute_mcp_action(*, task_id: str, dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("mcp_service")
    if service is None:
        raise RuntimeError("McpIntegrationService is required")
    result = await service.execute_task(
        task_service=runtime.get("task_service"),
        task_id=task_id,
        trace_id=dispatch["trace_id"],
        server_id=dispatch["server_id"],
        tool_name=dispatch["tool_name"],
        arguments=dispatch.get("arguments") or {},
    )
    return dict(result or {})
