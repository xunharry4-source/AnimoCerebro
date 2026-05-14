from __future__ import annotations

from typing import Any, Dict


async def execute_external_connector_action(*, task_id: str, dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("external_connector_service")
    if service is None:
        raise RuntimeError("ExternalConnectorService is required")
    executor = getattr(service, "execute_capability", None)
    if not callable(executor):
        if not dispatch.get("allow_legacy_test_call_adapter"):
            raise RuntimeError(
                "ExternalConnectorService.execute_capability is required for ReAct business execution; "
                "test_call cannot be used as a successful business execution path"
            )
        from zentex.external_connectors.models import ConnectorTestCallRequest

        invocation = service.test_call(
            dispatch["connector_id"],
            ConnectorTestCallRequest(
                capability=dispatch["capability"],
                arguments=dispatch.get("arguments") or {},
                trace_id=dispatch["trace_id"],
            ),
        )
        return {
            "succeeded": getattr(invocation, "status", "") == "success",
            "execution_api": "legacy_test_call_adapter",
            "result": invocation.model_dump(mode="json") if hasattr(invocation, "model_dump") else getattr(invocation, "__dict__", {}),
            "task_center_synchronized": False,
        }

    result = executor(
        dispatch["connector_id"],
        {
            "capability": dispatch["capability"],
            "arguments": dispatch.get("arguments") or {},
            "trace_id": dispatch["trace_id"],
            "task_id": task_id,
        },
    )
    if hasattr(result, "__await__"):
        result = await result
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result or {})
