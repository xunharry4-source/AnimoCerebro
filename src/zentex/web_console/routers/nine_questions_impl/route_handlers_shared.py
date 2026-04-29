from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import HTTPException, Request

from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service
from zentex.web_console.dependencies import get_plugin_service

logger = logging.getLogger(__name__)
_nine_question_execution_guard = threading.Lock()

QUESTION_TITLES = {
    "q1": "我在哪",
    "q2": "我是谁",
    "q3": "我有什么",
    "q4": "我能干什么",
    "q5": "我可以干什么",
    "q6": "我即使能做也不该做什么",
    "q7": "我还可以做什么",
    "q8": "我应该干什么",
    "q9": "我应该怎么做",
}


def acquire_nine_question_execution_guard() -> None:
    if _nine_question_execution_guard.acquire(blocking=False):
        return
    raise HTTPException(
        status_code=409,
        detail={
            "error": "nine_question_execution_in_progress",
            "message": "九问执行正在进行中，请等待当前执行完成后再试。",
        },
    )


def stringify_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def inject_app_runtime_context(request: Request, context: dict[str, Any]) -> dict[str, Any]:
    app_state = getattr(request.app, "state", None)
    enriched = dict(context)
    for key in (
        "foundation_service",
        "agent_service",
        "cli_service",
        "mcp_service",
        "memory_service",
        "audit_service",
        "reflection_service",
        "learning_service",
        "cognitive_tool_registry_runtime",
        "managed_plugin_records",
    ):
        if key not in enriched and app_state is not None and hasattr(app_state, key):
            enriched[key] = getattr(app_state, key)
    plugin_service = get_plugin_service(request)
    if plugin_service is not None:
        enriched["plugin_service"] = plugin_service
    return enriched


async def sync_q8_tasks(request: Request, session_id: str, snapshot_map: dict[str, dict[str, Any]]) -> None:
    await sync_q8_tasks_to_task_service(
        task_service=getattr(request.app.state, "task_service", None),
        session_id=session_id,
        snapshot_map=snapshot_map,
        logger=logger,
    )
