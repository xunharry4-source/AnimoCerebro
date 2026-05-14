from __future__ import annotations

from typing import Any, Dict


async def execute_cli_action(*, task_id: str, dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("cli_service")
    if service is None:
        raise RuntimeError("CliIntegrationService is required")
    task_service = runtime.get("task_service")
    result = await service.execute_task(
        task_service=task_service,
        task_id=task_id,
        trace_id=dispatch["trace_id"],
        tool_name=dispatch["tool_name"],
        arguments=dispatch.get("arguments") or [],
        stdin_input=dispatch.get("stdin_input"),
        working_directory=dispatch.get("working_directory"),
        timeout_seconds=float(dispatch.get("timeout_seconds") or runtime.get("execution_timeout_seconds") or 300.0),
    )
    return dict(result or {})
