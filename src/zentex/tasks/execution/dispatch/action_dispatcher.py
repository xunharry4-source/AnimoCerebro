from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from zentex.tasks.execution.dispatch.agent_adapter import execute_agent_action
from zentex.tasks.execution.dispatch.cli_adapter import execute_cli_action
from zentex.tasks.execution.dispatch.external_connector_adapter import execute_external_connector_action
from zentex.tasks.execution.dispatch.internal_plugin_adapter import execute_internal_plugin_action
from zentex.tasks.execution.dispatch.mcp_adapter import execute_mcp_action


async def dispatch_action(context: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
    executor_type = str(context.get("executor_type") or dispatch.get("executor_type") or "").strip()
    task_id = str(context.get("task_id") or "")
    attempt_id = f"react-attempt-{uuid4().hex}"
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        if executor_type == "cli":
            result = await execute_cli_action(task_id=task_id, dispatch=dispatch, runtime=runtime)
        elif executor_type == "mcp":
            result = await execute_mcp_action(task_id=task_id, dispatch=dispatch, runtime=runtime)
        elif executor_type == "external_connector":
            result = await execute_external_connector_action(task_id=task_id, dispatch=dispatch, runtime=runtime)
        elif executor_type == "agent":
            result = await execute_agent_action(task_id=task_id, dispatch=dispatch, runtime=runtime)
        elif executor_type == "internal_plugin":
            result = await execute_internal_plugin_action(task_id=task_id, dispatch=dispatch, runtime=runtime)
        else:
            raise RuntimeError(f"Unsupported executor type: {executor_type}")
        succeeded = bool(result.get("succeeded", result.get("status") in {"success", "completed"}))
        return {
            "attempt_id": attempt_id,
            "task_id": task_id,
            "trace_id": context.get("trace_id"),
            "executor_type": executor_type,
            "owner_ref": context.get("owner_ref"),
            "capability": context.get("capability"),
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "succeeded" if succeeded else "failed",
            "error_code": "" if succeeded else str(result.get("error_code") or "EXECUTOR_RESULT_FAILED"),
            "error_message": "" if succeeded else str(result.get("error") or result.get("message") or "Executor returned failed result"),
            "retryable": bool(result.get("retryable")),
            "result": result,
        }
    except Exception as exc:
        return {
            "attempt_id": attempt_id,
            "task_id": task_id,
            "trace_id": context.get("trace_id"),
            "executor_type": executor_type,
            "owner_ref": context.get("owner_ref"),
            "capability": context.get("capability"),
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "error_code": "ACTION_DISPATCH_FAILED",
            "error_message": str(exc),
            "retryable": False,
            "result": {},
        }
