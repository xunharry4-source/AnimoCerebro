from __future__ import annotations

from typing import Any, Dict


async def execute_internal_plugin_action(*, task_id: str, dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    executor = runtime.get("internal_executor")
    if executor is None:
        raise RuntimeError("InternalPluginExecutor is required")
    subtask_intent = runtime.get("subtask_intent")
    if subtask_intent is None:
        raise RuntimeError("SubtaskIntent is required for internal plugin execution")
    result = await executor.execute_on_plugin(dispatch["plugin_id"], subtask_intent, task_id)
    return dict(result or {})
