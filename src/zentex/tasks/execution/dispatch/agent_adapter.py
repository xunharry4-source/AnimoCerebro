from __future__ import annotations

from typing import Any, Dict


async def execute_agent_action(*, task_id: str, dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("agent_service")
    if service is None:
        raise RuntimeError("Agent coordination service is required")
    payload = dict(dispatch.get("task_payload") or {})
    payload.setdefault("zentex_task_id", task_id)
    response = await service.dispatch_task(
        dispatch["agent_id"],
        payload,
        verification_plan=dispatch.get("verification_plan"),
        zentex_task_id=task_id,
        idempotency_key=dispatch.get("idempotency_key"),
        cli_service=runtime.get("cli_service"),
        mcp_service=runtime.get("mcp_service"),
    )
    succeeded = not getattr(response, "is_error", False)
    return {
        "succeeded": succeeded,
        "task_center_synchronized": False,
        "result": getattr(response, "data", None),
        "error": None if succeeded else getattr(response, "message", "Agent dispatch failed"),
        "trace_id": getattr(response, "trace_id", None) or dispatch.get("trace_id"),
    }
